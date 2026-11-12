import re
from collections.abc import Callable
from random import Random
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article
from magic_cards_model.text_norm import collapsed

from ...models.card import Type
from ...models.card_state import (
    CardState,
    Choice,
    ChoiceKind,
)
from ...models.player import Player
from ...models.token import (
    create_tokens,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    count_pattern,
    parse_count,
    parse_quantity,
    quantity_pattern,
)
from ..abilities import (
    TriggerEvent,
)
from ..casting import (
    PlayAction,
)
from ..damage_backrefs import newly_discarded, public_card_ids
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    DelayedTrigger,
    DiscardCardsAtRandomForController,
    ReflexiveConsequence,
)
from ..designations import designation_holds, split_if
from ..ep01_r3_amounts import event_player_username
from ..ep02_r2_devotion_domain_party import discard_hand_draw_per_color_effect
from ..layers import (
    Characteristics,
)
from ..replacement import (
    DrawReplacementKind,
    NextTimeDrawReplacement,
    strip_reminder_text,
)
from ..triggers import (
    AbilityOnStack,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import AbilityEffect, ClauseEffect, Effect, TargetedClause


def draw_cards(count: int) -> Effect:
    """The spell's controller draws `count` cards (CR 121.1, CR 121.2).

    Routed through `Game.draw_cards`, so each card is its own individual draw
    (CR 121.2: "that player performs that many individual card draws") and its
    own trigger event - a Sheoldred watching "whenever you draw a card" sees
    one event per card, not one with a count.
    """

    def effect(game: "Game", spell: CardState) -> None:
        game.draw_cards(game.controller_of(spell).username, count)

    return effect


def _source_characteristic(game: "Game", source: CardState | None, characteristic: str) -> int:
    """The source's power or toughness now, or its last known value (CR
    608.2h) once it has left the battlefield; never below 0 as a magnitude."""
    if source is None:
        return 0
    if source.zone is Zone.BATTLEFIELD:
        value = game.power_of(source) if characteristic == "power" else game.toughness_of(source)
    else:
        power, toughness = source.last_known_power_toughness()
        value = power if characteristic == "power" else toughness
    return max(value or 0, 0)


#: "Discard N cards, then draw M cards. For each nonland card discarded this
#: way, create [a|N] <token descriptor> token(s)[ with <tail>]." - Seasoned
#: Pyromancer's whole enters-the-battlefield trigger, read as one CR 608.2c
#: instruction: the discard, then the draw, then the per-card token creation.
#: The discard and draw counts, and the token's own P/T, color and subtypes,
#: are read through `numbers.COUNT` and `_parse_generic_token_descriptor`
#: rather than pinned to Seasoned Pyromancer's own "two"/"two"/"1/1 red
#: Elemental", so a future card sharing this exact template - a different
#: discard count, draw count, or token - reads for free. "For each nonland
#: card discarded this way" is *not* itself a `numbers.COUNT` word - it is a
#: linked count over exactly the cards this discard put into the graveyard,
#: counted as they go rather than by looking at the graveyard afterwards,
#: same as before this row was replaced.
_DISCARD_THEN_DRAW_TOKEN_PER_NONLAND_RE = re.compile(
    rf"^discard {count_pattern('discard_n')} cards?,\s*then draw {count_pattern('draw_n')} "
    rf"cards?\.\s*for each nonland card discarded this way, create (?:a|an|{COUNT}) "
    r"(?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


#: "Draw a card for every `<n>` `<counted>`[. If you draw `<m>` or more cards
#: this way, `<consequence>`]" - Sarek, Federation Ambassador's "draw a card
#: for every five creature types among non-Borg creatures you control. If you
#: draw three or more cards this way, put two +1/+1 counters on each creature
#: you control." "For every five" draws one card per complete group of five
#: (no fractional card is drawn, CR 107.1a), so four types draw nothing and
#: nine draw one. "Draw ... this way" is CR 608.2c's anaphora: the
#: cards actually drawn, so a short library draws fewer.
_DRAW_A_CARD_FOR_EVERY_N_RE = re.compile(
    rf"^draw a card for every (?P<n>{COUNT}) (?P<counted>[^.]+?)\.?"
    rf"(?:\s*if you draw (?P<m>{COUNT}) or more cards this way,\s*(?P<then>[^.]+\.?))?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s16")
def _parse_draw_a_card_for_every_n_clause(text: str) -> AbilityEffect | None:
    """`_DRAW_A_CARD_FOR_EVERY_N_RE`'s shape, or `None`. The counted phrase
    is any `count_expression` "the number of `<counted>`"; the consequence
    any ability clause the dispatcher reads whole."""
    match = _DRAW_A_CARD_FOR_EVERY_N_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    per = parse_count(match.group("n"))
    counted = count_expression(f"the number of {match.group('counted')}")
    if not per or counted is None:
        return None
    threshold: int | None = None
    consequence: AbilityEffect | None = None
    if match.group("then") is not None:
        threshold = parse_count(match.group("m"))
        then_text = match.group("then").strip()
        then_text = then_text[0].upper() + then_text[1:]
        consequence = _ability_effect_or_notice(then_text)
        if threshold is None or consequence is None or _is_notice_only(consequence):
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        amount = counted(game, player.username) // per  # complete groups only
        drawn = game.draw_cards(player.username, amount) if amount > 0 else []
        if consequence is not None and threshold is not None and len(drawn) >= threshold:
            consequence(game, ability)

    return effect


@ABILITY_TEXT.rung("s16")
def _parse_discard_after_damage_dealt_this_way_ability(text: str) -> AbilityEffect | None:
    """Sonic Shrieker's whole enters-the-battlefield trigger: a damage head,
    then "If a player is dealt damage this way, they discard a card." - read by
    `damage_backrefs.damage_then_player_rider_ability_effect`, which owns the
    head and what damage actually reached."""
    from ..damage_backrefs import damage_then_player_rider_ability_effect

    return damage_then_player_rider_ability_effect(text)


@ABILITY_TEXT.rung("s16")
def _parse_discard_then_draw_token_per_nonland_clause(text: str) -> AbilityEffect | None:
    """`_DISCARD_THEN_DRAW_TOKEN_PER_NONLAND_RE`'s shape - Seasoned
    Pyromancer's whole enters-the-battlefield trigger.

    **Which cards are discarded is the discarding player's own choice**
    (CR 701.9b: "By default, effects that cause a player to discard a card allow
    the affected player to choose which card to discard"), so this is a
    `CHOOSE_CARDS` question through `Game.ask`, the same CR 608.2d machinery as
    the cleanup discard. The candidates are offered in *reverse* hand order so
    that the unscripted default - `default_answer`'s "back of the offered
    cards" - lands on the *front* of the hand, reproducing the old hardcoded
    `hand[:2]` byte for byte when nobody answers.
    """
    match = _DISCARD_THEN_DRAW_TOKEN_PER_NONLAND_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    discard_n = parse_count(match.group("discard_n"))
    draw_n = parse_count(match.group("draw_n"))
    if discard_n is None or draw_n is None:
        return None
    words = match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        hand = list(player.hand)
        amount = min(discard_n, len(hand))
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"choose {amount} card(s) to discard",
            source=ability.source_name,
            source_id=source_id_of(ability),
            amount=amount,
            cards=tuple(state.id for state in reversed(hand)),
        )
        chosen_ids = game.ask(decision)
        by_id = {state.id: state for state in hand}
        discarded = [by_id[card_id] for card_id in chosen_ids]
        # Through `Game.discard_cards` and `Game.draw_cards`, never `Player.discard`
        # / `Player.draw`: the `Player` methods move cards and nothing else, so a
        # discard performed that way raises no `DISCARDS_A_CARD` event (CR 701.9a is
        # only the move; the event is what a "whenever you discard" ability watches),
        # is not counted in `Game.cards_discarded_this_turn`, and gets no CR 702.35a
        # madness replacement - and a draw performed that way raises no
        # `DRAWS_A_CARD` and skips CR 121.6's draw replacements. CR 601.2f's cost
        # reduction is read off that discard count, so Hollow One was charged the
        # wrong price after a Pyromancer's discard until this routed through the
        # `Game`. CR 121.2 makes "draw two cards" two individual draws, which
        # `Game.draw_cards` performs one at a time.
        game.discard_cards(player.username, discarded, source=ability.source_name)
        game.draw_cards(player, draw_n)
        nonlands = sum(1 for state in discarded if not state.card.is_land)
        create_tokens(game, definition, ability.controller, nonlands)

    return effect


#: "Draw X cards, where X is `<count>`." - the same instruction as "Draw cards
#: equal to `<count>`" in its X form (Liliana's Standard Bearer's "draw X
#: cards, where X is the number of creatures that died under your control this
#: turn"). Only a `count_expression` the amounts family reads is accepted, so
#: an X naming something else ("the number of cards discarded this way") still
#: falls to its own reader.
_DRAW_X_WHERE_X_IS_RE = re.compile(r"^draw x cards, where x is (?P<expr>.+?)$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_draw_cards_equal_to_count_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Draw cards equal to `<count>`." on its own - Last March of the Ents'
    "Draw cards equal to the greatest toughness among creatures you control,
    then put ...". `_DRAW_CARDS_EQUAL_TO_RE` and `count_expression` are the
    ones Rise of the Deathbringer's own paired reader already uses; the
    amount is read once, as the instruction is applied (CR 608.2h), and an
    empty group is 0 (CR 107.2) - no draw at all."""
    text = clause.strip().rstrip(".").strip()
    match = _DRAW_CARDS_EQUAL_TO_RE.fullmatch(text) or _DRAW_X_WHERE_X_IS_RE.fullmatch(text)
    if match is None:
        return None
    counter = count_expression(match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = counter(game, controller.username)
        if amount > 0:
            game.draw_cards(controller.username, amount)

    return effect


#: Momentous Fall's whole second paragraph: "You draw cards equal to the
#: sacrificed creature's power, then you gain life equal to its toughness."
#:
#: Read whole, ahead of `split_effect_clauses`: the second half's "its" is
#: CR 400.7 anaphora back to the creature the *first* half named, and cut apart
#: the fragment "you gain life equal to its toughness" names nothing at all.
#: One CR 608.2c instruction, so it is one parser.
#:
#: Both numbers come off the creature that paid CR 118.8a's printed additional
#: cost, recorded in `Game.cast_record(spell).additional_cost_cards` the same
#: way `_deal_damage_equal_to_sacrificed_creature_power` reads Fling's.
_DRAW_AND_GAIN_OFF_SACRIFICED_RE = re.compile(
    r"^you draw cards equal to the sacrificed creature['’]s power, "
    r"then you gain life equal to its toughness\.?$",
    re.IGNORECASE,
)


def _parse_draw_and_gain_off_sacrificed_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DRAW_AND_GAIN_OFF_SACRIFICED_RE`'s shape - Momentous Fall.

    Spell-only: the numbers come off *this spell's* own cast record, and an
    ability has no additional cost and no cast record to read.

    **CR 608.2h is the rule this clause is really about**, and this engine can
    only half honour it: "If an effect requires information from the game ...
    the answer is determined only once, when the effect is applied." The
    creature is in its owner's graveyard by then - CR 601.2h paid the sacrifice
    before the spell was ever put on the stack - so the power and toughness
    wanted here are the ones it last had *on the battlefield*, not the ones a
    graveyard card computes now.

    What is read below is `CardState.power`/`.toughness`, which is the printed
    box plus counters (CR 122.1a). That is the same answer for a creature whose
    size on the battlefield came only from its printing and its counters -
    which is every card in this pool that pays this cost today - and the wrong
    answer for one whose size came from a continuous effect that stopped
    applying when it left (Omnath, Locus of Mana's own "+1/+1 for each unspent
    green mana you have", the whole point of DDR#955). `CardState` carries a
    `last_known_counters` snapshot for CR 704.8 but no last-known
    power/toughness, so there is nothing better to read yet; when there is,
    this is the one line that has to change.

    An absent power or toughness (no card recorded, or a printed `*` this
    engine cannot compute off a card that has left the battlefield) draws and
    gains zero rather than guessing. CR 121.3's empty-library loss is
    `Game.draw_cards`'s business, not this clause's.
    """
    if not for_spell:
        return None
    # `_strip_non_effect_preamble` first: Momentous Fall's own printed
    # additional-cost line ("As an additional cost to cast this spell,
    # sacrifice a creature.") is part of casting it (CR 601.2f/601.2h), not
    # part of its resolution, and it is already paid by the time this runs.
    stripped = collapsed(_strip_non_effect_preamble(text))
    if _DRAW_AND_GAIN_OFF_SACRIFICED_RE.fullmatch(stripped) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        record = game.cast_record(stack_object)
        sacrificed = None
        if record.additional_cost_cards:
            sacrificed = game.find_by_id(record.additional_cost_cards[0])
        power = 0 if sacrificed is None or sacrificed.power is None else max(sacrificed.power, 0)
        toughness = (
            0
            if sacrificed is None or sacrificed.toughness is None
            else max(sacrificed.toughness, 0)
        )
        if power:
            game.draw_cards(controller, power)
        if toughness:
            controller.gain_life(toughness)

    return effect


#: "[you may ]put `<quantity>` land card(s) from your hand onto the
#: battlefield[ tapped]" - Arboreal Grazer's whole trigger ("a land card",
#: `parse_quantity`'s plain 1) and Wrenn and Seven's loyalty 0 ("any number of
#: land cards", CR 107.1c's zero-or-more) are one shape with a different
#: printed quantity, not two - the pinned defect this wave fixes was that the
#: regex only ever matched the article "a" and `_choose_land_from_hand` only
#: ever asked for exactly one. (The first half of Cultivator Colossus's
#: longer, repeating "put a land card ... . If you do, ..." is still read
#: separately by `_PUT_LAND_FROM_HAND_REPEAT_RE` below, since "repeat this
#: process" needs the loop that clause's own dedicated parser builds, and it
#: is always the singular "a" - no printed variant of it counts otherwise.)
_PUT_LAND_FROM_HAND_RE = re.compile(
    rf"(?P<subject>you may )?put {quantity_pattern('n')} land cards? "
    r"from your hand onto the battlefield(?P<tapped> tapped)?\.?",
    re.IGNORECASE,
)


def _land_cards_in_hand(player: Player) -> list[CardState]:
    return [state for state in player.hand if Type.LAND in state.types]


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_put_land_from_hand_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_PUT_LAND_FROM_HAND_RE`'s shape - Arboreal Grazer's whole trigger, or
    Wrenn and Seven's loyalty 0.

    CR 110.5b: the land(s) arrive untapped unless the sentence says "tapped",
    not because this is a search (`_SEARCH_AND_PUT_RE`'s own default is the
    same, for the same reason). No land in hand at all leaves nothing to
    choose, so the "you may" is never even asked - CR 608.2d's choice has to
    be a real one.
    """
    match = _PUT_LAND_FROM_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quantity = parse_quantity(match.group("n"))
    if quantity is None:
        return None
    tapped = bool(match.group("tapped"))
    optional = bool((match.group("subject") or "").strip())

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if not _land_cards_in_hand(player):
            return
        if optional and not game.may(
            player,
            "put a land card from your hand onto the battlefield",
            source=source,
            source_id=source_id_of(stack_object),
        ):
            return
        chosen = _choose_lands_from_hand(
            game, player, source, quantity=quantity, source_id=source_id_of(stack_object)
        )
        for card_state in chosen:
            game.put_onto_battlefield(card_state, player.username, tapped=tapped)

    return effect


#: "You may put a[n] `<description>` card[ with mana value N or less] from
#: your hand onto the battlefield[ tapped].[ If you don't, `<effect>`.]" -
#: Origin of the Avengers' chapter II ("a Hero creature card with mana value 3
#: or less ... If you don't, draw a card.") and Warren
#: Instigator's "a Goblin creature card". The description is read by the
#: search-quality reader (`_search_quality_is_readable`, `_quality_matcher`);
#: any word it cannot place leaves the whole sentence unread. Tried
#: only once every other reader has passed, so it never takes a sentence one
#: of them already reads.
_MAY_PUT_CARD_FROM_HAND_RE = re.compile(
    r"^you may put an? (?P<desc>[^.]+?) card"
    r"(?: with mana value (?:(?P<mv>\d+) or less|equal to (?P<mv_eq>\d+)"
    # Anticausal Vestige: "less than or equal to the number of lands you control",
    # counted as the instruction is followed (CR 608.2h).
    r"|less than or equal to (?P<mv_expr>the number of [^.]+?)))?"
    r" from your hand onto the battlefield(?P<tapped> tapped)?"
    r"(?:\.\s*if you don'?t, (?P<otherwise>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_may_put_card_from_hand_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_MAY_PUT_CARD_FROM_HAND_RE`'s shape. CR 608.2d: the controller chooses
    whether and which, only among cards that qualify - a hand with none has
    nothing to choose, so the "you may" is not asked. CR 110.2a: it enters
    under their control. "If you don't" (CR 608.2c) runs the other effect when
    nothing was put onto the battlefield, for either reason."""
    match = _MAY_PUT_CARD_FROM_HAND_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    if not _search_quality_is_readable(match.group("desc")):
        return None
    matches = _quality_matcher(match.group("desc"))
    cap = int(match.group("mv")) if match.group("mv") else None
    # Aether Vial's "mana value equal to the number of charge counters" (CR 202.3),
    # the number already read in by `ep02_r1_counter_amounts`.
    exact = int(match.group("mv_eq")) if match.group("mv_eq") else None
    mv_counter = count_expression(match.group("mv_expr")) if match.group("mv_expr") else None
    if match.group("mv_expr") and mv_counter is None:
        return None
    tapped = match.group("tapped") is not None
    otherwise_text = match.group("otherwise")
    otherwise = (
        _parse_mixed_clauses(otherwise_text.strip() + ".", for_spell=for_spell)
        if otherwise_text
        else []
    )
    if otherwise is None:
        return None
    phrase = f"{match.group('desc')} card" + (
        f" with mana value {cap} or less"
        if cap is not None
        else f" with mana value equal to {exact}"
        if exact is not None
        else f" with mana value less than or equal to {match.group('mv_expr')}"
        if mv_counter is not None
        else ""
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        ceiling = mv_counter(game, player.username) if mv_counter is not None else cap

        def qualifies(card: CardState) -> bool:
            return (
                matches(card)
                and (ceiling is None or card.mana_value <= ceiling)
                and (exact is None or card.mana_value == exact)
            )

        candidates = [card for card in player.hand if qualifies(card)]
        put = False
        if candidates and game.may(
            player,
            f"put a {phrase} from your hand onto the battlefield",
            source=source,
            source_id=source_id,
            cards=candidates,
        ):
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"choose a {phrase} to put onto the battlefield",
                    source=source,
                    source_id=source_id,
                    amount=1,
                    cards=tuple(card.id for card in candidates),
                    default_cards=(candidates[0].id,),
                )
            )
            assert isinstance(chosen_ids, tuple)
            chosen = next(card for card in candidates if card.id == chosen_ids[0])
            game.put_onto_battlefield(chosen, player.username, tapped=tapped)
            put = True
        if not put:
            for clause in otherwise:
                clause(game, stack_object)
                game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: "Target `<opponent|player>` may put a[n] `<description>` card from
#: `<their|his or her>` hand onto the battlefield[ tapped]." - Wumpus
#: Aberration's own "target opponent may put a creature card from their hand
#: onto the battlefield.", the *targeted* twin of `_MAY_PUT_CARD_FROM_HAND_
#: RE`'s own "you may": there, CR 608.2d's choice is the resolving ability's
#: controller; here it is CR 601.2c's own chosen target, read the same way
#: `_TARGET_PLAYER_DISCARDS_RE`/`_TARGET_OPPONENT_SACRIFICE_GREATEST_MV_RE`
#: already read "target opponent"/"target player" as a player target rather
#: than an object one.
_TARGET_PLAYER_MAY_PUT_CARD_FROM_HAND_RE = re.compile(
    r"^target (?P<who>opponent|player) may put an? (?P<desc>[^.]+?) card"
    r"(?: with mana value (?P<mv>\d+) or less)?"
    r" from (?:their|his or her) hand onto the battlefield(?P<tapped> tapped)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_player_may_put_card_from_hand_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_MAY_PUT_CARD_FROM_HAND_RE`'s shape. CR 608.2d: the
    *target* chooses whether and which, only among cards that qualify - a
    hand with none has nothing to choose, so the "may" is not asked at all.
    CR 110.2a: it enters under the target's control, not this ability's
    controller's.
    """
    match = _TARGET_PLAYER_MAY_PUT_CARD_FROM_HAND_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('who')}", allow_player_targets=True):
        return None
    if not _search_quality_is_readable(match.group("desc")):
        return None
    matches = _quality_matcher(match.group("desc"))
    cap = int(match.group("mv")) if match.group("mv") else None
    tapped = match.group("tapped") is not None
    phrase = f"{match.group('desc')} card" + (
        f" with mana value {cap} or less" if cap is not None else ""
    )

    def qualifies(card: CardState) -> bool:
        return matches(card) and (cap is None or card.mana_value <= cap)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
        if not targets:
            return
        player = targets[0]
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        candidates = [card for card in player.hand if qualifies(card)]
        if not candidates or not game.may(
            player,
            f"put a {phrase} from your hand onto the battlefield",
            source=source,
            source_id=source_id,
            cards=candidates,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose a {phrase} to put onto the battlefield",
                source=source,
                source_id=source_id,
                amount=1,
                cards=tuple(card.id for card in candidates),
                default_cards=(candidates[0].id,),
            )
        )
        assert isinstance(chosen_ids, tuple)
        chosen = next(card for card in candidates if card.id == chosen_ids[0])
        game.put_onto_battlefield(chosen, player.username, tapped=tapped)

    return effect


#: Cultivator Colossus's own shape: "you may put a land card from your hand
#: onto the battlefield tapped. If you do, draw a card and repeat this
#: process." A reflexive "if you do" (CR 118.12) whose own consequence loops
#: back to the start of the same instruction, so it needs the whole
#: unsplit text, not `_parse_put_land_from_hand_clause`'s one-shot version.
#: The draw count is read through `numbers.COUNT` rather than pinned to
#: Cultivator Colossus's own "a", so a future card looping the same process
#: over a different draw count reads for free.
_PUT_LAND_FROM_HAND_REPEAT_RE = re.compile(
    rf"^you may put a land card from your hand onto the battlefield(?P<tapped> tapped)?\. "
    rf"if you do, draw {count_pattern('n')} cards? and repeat this process\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s16")
def _parse_put_land_from_hand_repeat_clause(text: str) -> AbilityEffect | None:
    """`_PUT_LAND_FROM_HAND_REPEAT_RE`'s shape.

    "Repeat this process" loops CR 608.2d's choice: offer the "you may", and
    for as long as the answer is yes and a land remains to choose, put it onto
    the battlefield, draw a card, and ask again. The loop ends the moment
    either runs out - a declined "may" or an empty hand of lands, whichever
    comes first, matching CR 107.1a's floor of nothing to choose.
    """
    match = _PUT_LAND_FROM_HAND_REPEAT_RE.fullmatch(text.strip())
    if match is None:
        return None
    tapped = bool(match.group("tapped"))
    draw_count = parse_count(match.group("n"))
    if draw_count is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        controller = game.controller_of(ability)
        source = ability.source_name
        while True:
            if not _land_cards_in_hand(controller):
                break
            if not game.may(
                controller,
                "put a land card from your hand onto the battlefield",
                source=source,
                source_id=source_id_of(ability),
            ):
                break
            chosen = _choose_land_from_hand(
                game, controller, source, source_id=source_id_of(ability)
            )
            game.put_onto_battlefield(chosen, controller.username, tapped=tapped)
            game.draw_cards(controller.username, draw_count)

    return effect


#: Spelunking's own first paragraph: "draw a card, then you may put a land
#: card from your hand onto the battlefield. If you put a Cave onto the
#: battlefield this way, you gain 4 life." Whole-text, ahead of the ordinary
#: clause splitter, the same as `_PUT_LAND_FROM_HAND_REPEAT_RE`: the trailing
#: "If you put a Cave ... this way" clause needs to know *which* land the
#: previous clause actually placed, which only survives if one function runs
#: both. No "tapped" is printed here at all - CR 110.5b's plain default
#: applies to the land placed this way, and Spelunking's own second paragraph
#: ("Lands you control enter untapped") is a separate static ability read by
#: `machines/replacement.py`, not part of this trigger's own effect.
#: The draw count and the life gain are both read through `numbers.COUNT`
#: rather than pinned to Spelunking's own "a" and "4", so a future card
#: sharing this exact template with a different draw or life count reads for
#: free.
_DRAW_THEN_PUT_LAND_CAVE_BONUS_RE = re.compile(
    rf"^draw {count_pattern('draw_n')} cards?, then you may put a land card from your hand "
    rf"onto the battlefield\.\s*"
    rf"if you put a cave onto the battlefield this way, you gain {count_pattern('life')} "
    r"life\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s16")
def _parse_draw_then_put_land_cave_bonus_clause(text: str) -> AbilityEffect | None:
    """`_DRAW_THEN_PUT_LAND_CAVE_BONUS_RE`'s shape - Spelunking's whole enters
    trigger. CR 305.6: "Cave" is a land subtype like any other, so `has_land_
    type("Cave")` is the same check a search naming a land type would use -
    except that the question is asked of the *permanent* the land has just
    become, so it reads the computed board (CR 613.5) rather than the card's
    printed type line. "If you put a Cave onto the battlefield this way" is
    about what arrived: a Blood Moon (CR 305.7 sets a nonbasic land's subtype)
    makes it a Mountain the instant it does, Cave or not in hand.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _DRAW_THEN_PUT_LAND_CAVE_BONUS_RE.fullmatch(whole)
    if match is None:
        return None
    draw_count = parse_count(match.group("draw_n"))
    life = parse_count(match.group("life"))
    if draw_count is None or life is None:
        return None

    def is_cave(chars: Characteristics) -> bool:
        return "cave" in {subtype.lower() for subtype in chars.subtypes}

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        controller = game.controller_of(ability)
        source = ability.source_name
        game.draw_cards(controller.username, draw_count)
        if not _land_cards_in_hand(controller):
            return
        if not game.may(
            controller,
            "put a land card from your hand onto the battlefield",
            source=source,
            source_id=source_id_of(ability),
        ):
            return
        chosen = _choose_land_from_hand(game, controller, source, source_id=source_id_of(ability))
        game.put_onto_battlefield(chosen, controller.username, tapped=False)
        if is_cave(game.characteristics_of(chosen)):
            game.gain_life(controller, life)

    return effect


#: "Discard that many cards." - Marina Vendrell's Grimoire's "Whenever you
#: lose life, discard that many cards." The count is the triggering event's
#: own amount (`amounts.that_many`, CR 603.2c), discarded by the controller
#: (CR 701.9a/b: their choice; fewer in hand discards them all).
_DISCARD_THAT_MANY_RE = re.compile(r"^discard that many cards\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s20")
def _parse_discard_that_many_clause(text: str) -> AbilityEffect | None:
    """`_DISCARD_THAT_MANY_RE`'s shape, or `None`."""
    if _DISCARD_THAT_MANY_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        count = _that_many_or_notice(
            game,
            text,
            source_id=ability.source_id,
            source_name=ability.source_name,
            stack_object=ability,
        )
        if not count:
            return
        player = game.player(ability.controller)
        _discard_cards(
            game,
            player,
            min(count, len(player.hand)),
            ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


#: "Draw an additional card and remove N `<kind>` counters from this
#: `<noun>`." - Midnight Oil's draw-step trigger: two instructions joined by
#: "and", each an ordinary clause read on its own and followed in order
#: (CR 608.2c).
_DRAW_AND_REMOVE_COUNTERS_RE = re.compile(
    r"^(?P<draw>draw [^.]+?) and (?P<remove>remove [^.]+? counters? from this [a-z]+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_draw_and_remove_counters_clause(text: str) -> AbilityEffect | None:
    """`_DRAW_AND_REMOVE_COUNTERS_RE`'s shape, or `None`."""
    match = _DRAW_AND_REMOVE_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    draw = parse_mixed_effect(match.group("draw").strip() + ".")
    remove = _ability_effect_or_notice(match.group("remove").strip() + ".")
    if draw is None or remove is None or _is_notice_only(remove):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        draw(game, ability)
        remove(game, ability)

    return effect


def _discard_cards(
    game: "Game",
    player: Player,
    count: int,
    source: str,
    *,
    source_id: str | None,
    exact: bool = True,
    predicate: Callable[[CardState], bool] | None = None,
) -> list[CardState]:
    """CR 701.9a/701.9b: `player` discards `count` cards of their own choice -
    exactly `count` when `exact` is `True` (every caller before "up to N"/"any
    number of" discards existed), or CR 107.1c's own "any positive number or
    zero" up to `count` when it is `False` (Fable of the Mirror-Breaker's own
    "you may discard up to two cards").

    `predicate`, when given, narrows both the pool offered and the floor
    below to only the cards satisfying it - Borborygmos and Fblthp's own
    "discard any number of land cards" (CR 701.9b's "the affected player
    chooses which card" narrowed the identical way `_nonland_or_typed_card_
    matcher` already narrows a *search*). `None` is every existing caller,
    unchanged.

    A hand shorter than `count` (or, with `predicate`, a matching-card pool
    shorter than `count`) is not a violation - the player discards as many
    as they have, one card at a time, the same floor
    `_parse_target_player_discards_clause` already applies to a discard the
    resolving spell aims at someone else.

    Returns the cards actually discarded, so a caller whose own clause asks a
    question *about* them - CR 701.70a's recruit ("if you discarded a nonland
    card this way"), Winternight Stories' "unless you discard a creature
    card" - can read the answer off the move rather than re-deriving it.
    Every existing caller ignores the value, exactly as before.
    """
    pool = [card for card in player.hand if predicate is None or predicate(card)]
    needed = min(count, len(pool))
    if needed <= 0:
        game.record_count(0)
        return []
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"discard {'up to ' if not exact else ''}{needed} card(s)",
            source=source,
            amount=needed,
            cards=tuple(state.id for state in pool),
            source_id=source_id,
            exact=exact,
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in pool}
    discarded = game.discard_cards(
        player.username, [by_id[card_id] for card_id in chosen_ids], source=source
    )
    # CR 608.2c: a later "that many" (Jaya Ballard's "then draw that many
    # cards") is the number actually discarded, not the printed ceiling.
    game.record_count(len(discarded))
    return discarded


#: "discard a card unless `<condition>`" - Moon-Circuit Hacker's "discard a
#: card unless this creature entered this turn", Kaito Shizuki's "Then discard
#: a card unless you attacked this turn". CR 118.12a reads "[Do something]
#: unless [...]" as the something happening only when the other thing did
#: not; here the other thing is a board fact `Game.condition_holds` reads.
_DISCARD_UNLESS_CONDITION_RE = re.compile(
    r"^(?:then )?(?P<discard>discards? .+?) unless (?P<condition>.+)$", re.IGNORECASE
)


def _parse_discard_unless_condition_clause(clause: str) -> ClauseEffect | None:
    """`_DISCARD_UNLESS_CONDITION_RE`'s shape: the discard is any shape
    `_DISCARD_A_CARD_RE` reads, and the condition must be one
    `condition_is_readable` knows at parse time. The condition is asked of the
    resolving ability's own source (`source_id`) - a self-reference like
    "this creature entered this turn" reads its last known state when it has
    left the battlefield (CR 608.2h). An answer `condition_holds` still cannot
    give records a `ConditionalClauseNotice` and discards nothing."""

    match = _DISCARD_UNLESS_CONDITION_RE.fullmatch(clause)
    if match is None:
        return None
    discard_text = match.group("discard").strip()
    condition = match.group("condition").strip()
    if _DISCARD_A_CARD_RE.fullmatch(discard_text) is None or not _effect_condition_is_readable(
        condition
    ):
        return None
    discard = parse_clause_effect(discard_text)
    if discard is None:
        return None

    def discard_unless(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        source_state = game.find_by_id(UUID(source_id)) if source_id is not None else None
        held = game.condition_holds(player.username, condition, source_state)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=UUID(source_id) if source_id is not None else None,
                source_name=source,
                text=clause,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if not held:
            discard(game, player, source, source_id)

    return discard_unless


#: "Choose target player. They may discard up to X cards. Then they draw a card
#: for each card discarded this way." (Mishra's Command, mode 1) - the target
#: player, not the controller, discards and draws.
_TARGET_PLAYER_MAY_DISCARD_UP_TO_THEN_DRAW_RE = re.compile(
    rf"^(?:choose )?target player\.? they may discard up to (?P<n>x|{COUNT}) cards?\.? "
    r"then they draw a card for each card discarded this way\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_target_player_may_discard_up_to_then_draw_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_TARGET_PLAYER_MAY_DISCARD_UP_TO_THEN_DRAW_RE`'s whole instruction. The
    ceiling is a printed count (a modal spell's X is already substituted into
    the mode text, CR 107.3a) or, unsubstituted, X from the cast record; the
    target chooses zero up to that many of their own cards (CR 107.1c, CR
    701.9b) and draws exactly as many as were discarded (CR 608.2c's "this
    way")."""
    if "discarded this way" not in text.lower():
        return None
    whole = collapsed(_strip_non_effect_preamble(text))
    match = _TARGET_PLAYER_MAY_DISCARD_UP_TO_THEN_DRAW_RE.fullmatch(whole)
    if match is None or not _targets_understood("target player", allow_player_targets=True):
        return None
    x_ceiling = match.group("n").lower() == "x"
    printed = None if x_ceiling else parse_count(match.group("n"))
    if printed is None and not x_ceiling:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ceiling = (
            game.cast_record(stack_object).x_value if printed is None else printed  # type: ignore[arg-type]
        )
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            discarded = _discard_cards(
                game, target, ceiling, source, source_id=source_id_of(stack_object), exact=False
            )
            if discarded:
                game.draw_cards(target.username, len(discarded))

    return [effect]


#: "each opponent draws a card" (Armor Wars' chapter I) - CR 121.2's draw by
#: every opponent of the clause's player, CR 121.2c's turn order (the active
#: player's draws first) among them.
_EACH_OPPONENT_DRAWS_RE = re.compile(
    rf"^each opponent draws (?:a card|(?P<n>{COUNT}) cards)$", re.IGNORECASE
)


def _each_opponent_draws_clause(clause: str) -> ClauseEffect | None:
    """`_EACH_OPPONENT_DRAWS_RE`'s draw, or `None`."""
    match = _EACH_OPPONENT_DRAWS_RE.fullmatch(clause)
    if match is None:
        return None
    count = parse_count(match.group("n")) if match.group("n") else 1
    if count is None:
        return None

    def each_opponent_draws(
        game: "Game", player: Player, source: str, source_id: str | None
    ) -> None:
        for opponent in _players_in_apnap_order(game):
            if opponent.username != player.username:
                game.draw_cards(opponent.username, count)

    return each_opponent_draws


def _discard_at_random(game: "Game", player: Player, count: int, source: str) -> None:
    """CR 701.9b's random discard: `count` cards go, with no
    decision asked of anybody.

    A hand shorter than `count` discards the whole hand, the same floor
    `_discard_cards` applies to a chosen discard. The randomness reuses
    `Game.shuffle_library`'s reproducible seed rather than a bare `Random()`,
    so a scenario asserting on which cards went stays deterministic.
    """
    hand = list(player.hand)
    if not hand:
        return
    rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:discard-at-random")  # noqa: S311
    rng.shuffle(hand)
    game.shuffles_performed += 1
    game.discard_cards(player.username, hand[:count], source=source)


#: "Draw X cards, where X is the number of cards that were put into target
#: player's graveyard from their library this turn." - Cruel Calculations,
#: whole. CR 608.2h's X is fixed once, at resolution, against whichever
#: player the spell's own single target names - not the caster
#: `count_expression`'s ordinary "you"/`controller` readers always mean -
#: which is why this is its own reader rather than a `count_expression`
#: term: no other card in the pool defines a magnitude against a *target*
#: player's own history (verified against Scryfall full-text search in the
#: session that wrote this; recorded here rather than asserted, the same
#: "no off-set second printing found" precedent `_parse_untap_trigger_
#: subject_clause`'s own sibling `_parse_landfall_type_then_add_mana_
#: clause_pair` already sets in `machines/triggers.py`). `Game.cards_put_
#: into_graveyard_this_turn`'s own `from_zone=Zone.LIBRARY` filter is what
#: a mill's own "cards put into a graveyard from a library" already reads
#: (CR 700.11's Descend uses the same ledger's `permanent_only` filter);
#: this is the first caller to read the `from_zone` half of it.
_DRAW_X_FROM_TARGET_GRAVEYARD_FROM_LIBRARY_RE = re.compile(
    r"^draw x cards?, where x is the number of cards (?:that )?were put into "
    r"target player'?s graveyard from (?:their|its) library this turn\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s10")
def _parse_draw_x_from_target_graveyard_from_library_clause(text: str) -> Effect | None:
    """`_DRAW_X_FROM_TARGET_GRAVEYARD_FROM_LIBRARY_RE`'s shape - see the
    banner above."""
    whole = collapsed(text.strip())
    if _DRAW_X_FROM_TARGET_GRAVEYARD_FROM_LIBRARY_RE.fullmatch(whole) is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        target = next((t for t in game.resolve_targets(spell) if isinstance(t, Player)), None)
        if target is None:
            return
        amount = game.cards_put_into_graveyard_this_turn(target.username, from_zone=Zone.LIBRARY)
        if amount > 0:
            game.draw_cards(controller.username, amount)

    return effect


#: Mathemagics: "Target player draws 2ˣ cards. (2⁰ = 1, 2¹ = 2, 2² = 4, ...)"
#: - the one power-of-two amount in the pool, read off `CastRecord.x_value`
#: (CR 107.3a, `{X}{X}{U}{U}` already carries an ordinary announced X) rather
#: than a literal or a "where X is" expression. Matched against the literal
#: printed superscript digit (U+00B2 etc.) `add_card.py` fetched verbatim
#: from Scryfall, after `strip_reminder_text` drops the parenthetical - CR
#: 207.2's reminder text is not part of the instruction.
_POWER_OF_TWO_DRAW_RE = re.compile(r"^target player draws 2ˣ cards\.?$", re.IGNORECASE)


@SPELL_TEXT.rung("s14")
def _parse_power_of_two_draw_clause(effect_text: str) -> Effect | None:
    """`_POWER_OF_TWO_DRAW_RE`'s shape, or `None`."""
    rules_text, _reminder = strip_reminder_text(effect_text.strip())
    if _POWER_OF_TWO_DRAW_RE.fullmatch(rules_text.strip()) is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        amount = 2**x_value if x_value >= 0 else 0
        if amount <= 0:
            return
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                game.draw_cards(target.username, amount)

    return effect


#: "Draw cards equal to the number of cards in target opponent's/player's
#: hand." - Recurring Insight's own whole spell, Borrowed Knowledge's own
#: first mode's own tail. Not `count_expression`'s "the number of cards in
#: your hand" (`_COUNT_CARDS_IN_YOUR_HAND_RE`): that reader's own signature,
#: `(game, controller) -> int`, has nowhere to carry a resolved *target* -
#: this reads a card in *someone else's* hand, so it goes through `Game.
#: resolve_targets` directly instead, the same way every other target-scoped
#: amount in this file (Fling's sacrificed creature, Combustion Technique's
#: expression) reads what a bare count expression cannot.
_DRAW_CARDS_EQUAL_TO_TARGET_HAND_RE = re.compile(
    r"^draws? cards? equal to the number of cards in target "
    r"(?P<subject>opponent|player)'?s hand$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_draw_cards_equal_to_target_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DRAW_CARDS_EQUAL_TO_TARGET_HAND_RE`'s shape, or `None`."""
    match = _DRAW_CARDS_EQUAL_TO_TARGET_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    phrase = f"target {match.group('subject')}"
    if not _targets_understood(phrase, allow_player_targets=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
        # CR 608.2b: a target gone by resolution leaves nothing to count -
        # the same "no event" every other library-count effect gives a
        # target that fizzled.
        if not targets:
            return
        (target,) = targets
        amount = len(target.hand)
        if amount <= 0:
            return
        game.draw_cards(controller.username, amount)

    return effect


#: "You lose life equal to the number of cards drawn this way." - the CR
#: 607.1 anaphora back to whatever the first sentence just drew, resolved
#: through the *actual* number of cards drawn (CR 121.4: drawing from an
#: empty library draws as many as are left, never more), not the requested
#: magnitude.
_LOSE_LIFE_EQUAL_TO_DRAWN_RE = re.compile(
    r"^you lose life equal to the number of cards drawn this way$", re.IGNORECASE
)


def _parse_draw_equal_to_then_lose_life_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Draw cards equal to `<expr>`. You lose life equal to the number of
    cards drawn this way." - Rise of the Deathbringer's own mode 1.

    Read as a pair, not two independent clauses, for the identical CR 607.1
    reason `_parse_object_anaphor_clause_pair` reads its own antecedent/rider
    pairs together: the life loss has no meaning apart from what the draw
    just did.
    """
    draw_match = _DRAW_CARDS_EQUAL_TO_RE.fullmatch(first.strip().rstrip(".").strip())
    if draw_match is None:
        return None
    if not _LOSE_LIFE_EQUAL_TO_DRAWN_RE.fullmatch(second.strip().rstrip(".").strip()):
        return None
    counter = count_expression(draw_match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = counter(game, controller.username)
        if amount <= 0:
            return
        drawn = game.draw_cards(controller.username, amount)
        if drawn:
            game.lose_life(controller, len(drawn))

    return effect


#: "Put up to one land card discarded this way onto the battlefield[
#: tapped] under your control." - Mind Roots' own second sentence. CR 607.1
#: anaphora over the very cards the first sentence's discard just moved -
#: never a second target or a search - so it is read as this pair's own
#: `_TARGET_PLAYER_DISCARDS_RE` antecedent's rider, not independently: "this
#: way" has no meaning apart from what that discard actually moved.
_PUT_UP_TO_ONE_LAND_DISCARDED_THIS_WAY_RE = re.compile(
    r"^put up to one land card discarded this way onto the battlefield"
    r"(?P<tapped> tapped)? under your control$",
    re.IGNORECASE,
)


def _parse_target_player_discards_then_play_land_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Mind Roots' whole spell: "Target player discards two cards. Put up to
    one land card discarded this way onto the battlefield tapped under your
    control."

    Read as one CR 608.2c pair rather than `_parse_target_player_discards_
    clause` plus an independent second clause: "discarded this way" names
    exactly the cards *that* discard moved - not `counted_this_way`'s bare
    int (this needs the actual cards, to know which of them are lands), and
    not a fresh count-based question. The land is put onto the battlefield
    under the **resolving spell's own controller's** control (CR 110.2a
    names who controls a permanent an effect puts onto the battlefield with
    nobody else named "your"), never the discarding target player's, which
    is why this stays its own reader rather than a rider bolted onto
    `_parse_target_player_discards_clause`'s per-target loop (that function's
    `player` argument there is the target, not "you").
    """
    discard_match = _TARGET_PLAYER_DISCARDS_RE.fullmatch(first.strip().rstrip(".").strip())
    if discard_match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    count = parse_count(discard_match.group("count"))
    if count is None:
        return None
    land_match = _PUT_UP_TO_ONE_LAND_DISCARDED_THIS_WAY_RE.fullmatch(
        second.strip().rstrip(".").strip()
    )
    if land_match is None:
        return None
    tapped = land_match.group("tapped") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
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
                    prompt=f"discard {needed} card(s)",
                    source=source,
                    amount=needed,
                    cards=tuple(state.id for state in target.hand),
                    source_id=source_id,
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in target.hand}
            discarded = game.discard_cards(
                target.username, [by_id[card_id] for card_id in chosen_ids], source=source
            )
            land_cards = [
                state
                for state in discarded
                if Type.LAND in state.types and state.zone is Zone.GRAVEYARD
            ]
            if not land_cards:
                continue
            chosen_land_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="put up to one land card discarded this way onto the battlefield",
                    source=source,
                    amount=1,
                    exact=False,
                    cards=tuple(state.id for state in land_cards),
                    source_id=source_id,
                )
            )
            assert isinstance(chosen_land_ids, tuple)
            by_land_id = {state.id: state for state in land_cards}
            for land_id in chosen_land_ids:
                land = by_land_id.get(land_id)
                if land is not None and land.zone is Zone.GRAVEYARD:
                    game.put_onto_battlefield(land, controller.username, tapped=tapped)

    return effect


#: "Each `<player|opponent>` discards `<n>` cards." - Garruk, Veiled
#: Butcher's own `−3` first sentence, and Strongarm Tactics' own "each player
#: discards a card" (`who` covers both CR 102.2 groups).
_EACH_GROUP_DISCARDS_N_RE = re.compile(
    rf"^each (?P<who>player|opponent) discards (?P<n>{COUNT}) cards?\.?$", re.IGNORECASE
)

#: "For each `<player|opponent>` who didn't discard `<n>` `<quality>` cards
#: this way, you draw `<m>` card(s)." - Garruk, Veiled Butcher's own second
#: sentence: a count of the *failing* members, applied once to this ability's
#: own controller. CR 608.2c anaphora ("this way") onto the discard the first
#: sentence just performed.
_FOR_EACH_WHO_DIDNT_DISCARD_QUALITY_YOU_DRAW_RE = re.compile(
    rf"^for each (?P<who>player|opponent) who didn'?t discard (?P<n>{COUNT}) (?P<quality>[a-z]+) "
    rf"cards? this way, you draw (?:a card|(?P<draw_n>{COUNT}) cards?)\.?$",
    re.IGNORECASE,
)

#: "Then each `<player|opponent>` who didn't discard `<n>` `<quality>` card(s)
#: this way loses `<m>` life." - Strongarm Tactics' own second sentence: the
#: consequence lands on each *failing member themselves*, not on this
#: ability's controller, the shape Garruk's own "you draw" is not (CR 119.3).
_THEN_EACH_WHO_DIDNT_DISCARD_QUALITY_LOSES_LIFE_RE = re.compile(
    rf"^then each (?P<who>player|opponent) who didn'?t discard (?P<n>{COUNT}) (?P<quality>[a-z]+) "
    rf"cards? this way loses (?P<life>{COUNT}) life\.?$",
    re.IGNORECASE,
)


def _parse_each_group_discards_then_consequence_per_failure_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Garruk, Veiled Butcher's own `−3`: "Each opponent discards two cards.
    For each opponent who didn't discard two nonland cards this way, you
    draw a card." Strongarm Tactics prints the same shape with "each player",
    a different quality, and a per-failing-member life loss in place of
    Garruk's own controller-side draw.

    Each discarding member still makes their own CR 701.9b choice of which
    cards to discard; whether that choice actually reached `<quality>` `<n>`
    times is read back off `_discard_cards`'s own return value and compared
    per member - "this way" is CR 608.2c anaphora onto exactly the discard
    the first sentence just performed, not a fresh discard of the resolving
    ability's own controller's choosing, so the two sentences have to run as
    one merge rather than as two independent clauses.
    """
    discard_match = _EACH_GROUP_DISCARDS_N_RE.fullmatch(first.strip())
    if discard_match is None:
        return None
    discard_who = discard_match.group("who").lower()
    discard_count = parse_count(discard_match.group("n"))
    if discard_count is None:
        return None

    draw_match = _FOR_EACH_WHO_DIDNT_DISCARD_QUALITY_YOU_DRAW_RE.fullmatch(second.strip())
    if draw_match is not None and draw_match.group("who").lower() == discard_who:
        threshold = parse_count(draw_match.group("n"))
        quality_matches = _nonland_or_typed_card_matcher(draw_match.group("quality"))
        draw_each = parse_count(draw_match.group("draw_n")) if draw_match.group("draw_n") else 1
        if threshold is None or quality_matches is None or draw_each is None:
            return None

        def draw_consequence(
            game: "Game",
            controller: Player,
            group: list[Player],
            source: str,
            source_id: str | None,
        ) -> None:
            failures = 0
            for member in group:
                discarded = _discard_cards(
                    game, member, discard_count, source, source_id=source_id, exact=True
                )
                matched = sum(1 for state in discarded if quality_matches(state))
                if matched < threshold:
                    failures += 1
            if failures:
                game.draw_cards(controller.username, failures * draw_each)

        consequence = draw_consequence
    elif (cant := _who_cant_discard_consequence(second, discard_who, discard_count)) is not None:
        consequence = cant
    else:
        life_match = _THEN_EACH_WHO_DIDNT_DISCARD_QUALITY_LOSES_LIFE_RE.fullmatch(second.strip())
        if life_match is None or life_match.group("who").lower() != discard_who:
            return None
        threshold = parse_count(life_match.group("n"))
        quality_matches = _nonland_or_typed_card_matcher(life_match.group("quality"))
        life_loss = parse_count(life_match.group("life"))
        if threshold is None or quality_matches is None or life_loss is None:
            return None

        def life_consequence(
            game: "Game",
            controller: Player,
            group: list[Player],
            source: str,
            source_id: str | None,
        ) -> None:
            for member in group:
                discarded = _discard_cards(
                    game, member, discard_count, source, source_id=source_id, exact=True
                )
                matched = sum(1 for state in discarded if quality_matches(state))
                if matched < threshold:
                    game.lose_life(member, life_loss)

        consequence = life_consequence

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        group = (
            game.players_in_game
            if discard_who == "player"
            else _opponents(game, controller.username)
        )
        consequence(game, controller, group, source, source_id)

    return effect


#: "You may discard a card or sacrifice a land. If you do, draw two cards."
#: (Highway Robbery) and the halves the other way round, "You may sacrifice an
#: artifact or discard a card. If you do, ..." (Vision of Love, K'un-Lun
#: Warrior, Reckless Detective) - CR 118.12's optional cost, payable two ways.
_MAY_DISCARD_OR_SACRIFICE_IF_YOU_DO_RE = re.compile(
    rf"^you may (?:discard (?P<discard_first>{COUNT}) cards? "
    r"or sacrifice (?P<restriction_last>[^.]+?)"
    rf"|sacrifice (?P<restriction_first>[^.]+?) or discard (?P<discard_last>{COUNT}) cards?)"
    r"\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s19", for_spell=False)
@SPELL_TEXT.rung("s15", for_spell=True)
def _parse_may_discard_or_sacrifice_if_you_do_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_MAY_DISCARD_OR_SACRIFICE_IF_YOU_DO_RE`'s shape.

    One "you may" (CR 118.12), legal to accept only when at least one half
    can be paid (CR 608.2d: a cost is paid in full or not at all, so a hand
    shorter than the discard count or no permanent matching the restriction
    removes that half). When both halves are payable the player then picks
    one (`CHOOSE_A_QUALITY`, options in printed order); when only one is,
    that one is paid with no second question. The consequence runs only once
    the chosen half was actually paid.
    """
    match = _MAY_DISCARD_OR_SACRIFICE_IF_YOU_DO_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    discard_text = match.group("discard_first") or match.group("discard_last")
    discard_n = parse_count(discard_text)
    restriction_text = (match.group("restriction_last") or match.group("restriction_first")).strip()
    restriction = _sacrifice_restriction(restriction_text)
    if discard_n is None or discard_n < 1 or restriction is None:
        return None
    consequence_text = match.group("consequence").strip()
    if re.search(r"\botherwise\b", consequence_text, re.IGNORECASE):
        return None
    consequence = (
        parse_mixed_effect_for_spell(consequence_text)
        if for_spell
        else parse_mixed_effect(consequence_text)
    )
    if consequence is None:
        return None
    discard_option = f"discard {discard_text.lower()} card{'s' if discard_n > 1 else ''}"
    sacrifice_option = f"sacrifice {restriction_text}"
    discard_printed_first = match.group("discard_first") is not None
    printed_order = (
        (discard_option, sacrifice_option)
        if discard_printed_first
        else (sacrifice_option, discard_option)
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        permanent_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = restriction.candidates(game, player, permanent_id)
        payable = {
            discard_option: len(player.hand) >= discard_n,
            sacrifice_option: _sacrifice_is_payable(restriction.quantity, candidates),
        }
        options = tuple(option for option in printed_order if payable[option])
        if not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=" or ".join(printed_order),
                source=source_name,
                affirmative_is_legal=bool(options),
                source_id=source_id_of(stack_object),
            )
        ):
            return
        chosen = options[0]
        if len(options) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=player.username,
                    prompt="choose which to do",
                    source=source_name,
                    options=options,
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(answer, str)
            chosen = answer
        if chosen == discard_option:
            discarded = _discard_cards(
                game, player, discard_n, source_name, source_id=source_id_of(stack_object)
            )
            if len(discarded) < discard_n:
                return
        else:
            sacrificed = _choose_permanents_to_sacrifice(
                game,
                player,
                restriction,
                candidates,
                source_name=source_name,
                source_id=source_id_of(stack_object),
            )
            if not sacrificed:
                return
            for permanent in sacrificed:
                game.sacrifice(permanent)
        consequence(game, stack_object)  # type: ignore[arg-type]

    return effect


#: "You may discard your hand. Draw X cards, where X is the number of cards
#: discarded this way. If you have an enduring story, Balin deals X damage to
#: each opponent." (Balin, Loremaster) - one CR 608.2c sequence: the optional
#: discard of the whole hand (CR 701.9a, CR 608.2d), a draw of exactly what
#: that discard moved, and an optional rider behind a designation
#: (`machines/designations.py`, checked as it is reached) dealing that same X
#: to each opponent (CR 120.3a). The rider's subject is the ability's own
#: source, whatever name it prints.
_DISCARD_HAND_DRAW_X_RE = re.compile(
    r"^you may discard your hand\.\s*"
    r"draw x cards, where x is the number of cards discarded this way"
    r"(?:\.\s*(?P<rider>if [^,]+, [^,.]+? deals x damage to each opponent))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_discard_hand_draw_x_clause(text: str) -> AbilityEffect | None:
    """`_DISCARD_HAND_DRAW_X_RE`'s shape, or None - an unreadable rider
    condition reads nothing rather than dropping the rider."""
    match = _DISCARD_HAND_DRAW_X_RE.fullmatch(text.strip())
    if match is None:
        return None
    condition: str | None = None
    if match.group("rider") is not None:
        split = split_if(match.group("rider"))
        if split is None:
            return None
        condition = split[0]

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        discarded = 0
        if game.may(
            controller,
            "discard your hand",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            hand = list(controller.hand)
            if hand:
                discarded = len(
                    game.discard_cards(controller.username, hand, source=ability.source_name)
                )
        # CR 608.2c: X is what the discard actually moved - none when declined.
        game.record_count(discarded)
        if discarded:
            game.draw_cards(controller.username, discarded)
        if condition is None or not discarded:
            return
        if designation_holds(condition, controller):
            source = ability.source_or_last_known(game)
            for opponent in _opponents(game, ability.controller):
                game.deal_damage(opponent, discarded, source=source)

    return effect


@ABILITY_TEXT.rung("s35")
def _parse_discard_hand_draw_per_color_clause(text: str) -> AbilityEffect | None:
    """ "You may discard your hand. If you do, draw a card for each of that spell's colors."
    (`ep02_r2_devotion_domain_party`)."""
    return discard_hand_draw_per_color_effect(text)


#: "draw cards equal to the difference" - The Ten Rings', Doctor Octopus,
#: Master Planner's and Kozilek, the Great Distortion's, whose intervening if
#: (CR 603.4) names the other number: "if you have fewer than ten cards in
#: hand". The difference is read as the ability resolves (CR 608.2h).
_DRAW_THE_DIFFERENCE_RE = re.compile(r"^(?:you )?draw cards equal to the difference\.?$", re.I)
_FEWER_THAN_N_CARDS_IN_HAND_RE = re.compile(
    rf"^you have fewer than (?P<n>{COUNT}) cards in (?:your )?hand$", re.IGNORECASE
)


#: "Discard all the cards in your hand" (Fateful Showdown, Shattered
#: Perception, Heartwarming Redemption, Soratami Seer) - the same instruction
#: as "Discard your hand" with the cards spelled out: CR 701.9a's discard of
#: every card the hand holds as it resolves, and the count a later "that many"
#: reads is what was actually discarded (CR 608.2c).
_DISCARD_ALL_CARDS_IN_HAND_RE = re.compile(
    r"^discard all (?:the )?cards in your hand\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s4", for_spell=FORWARD)
def _parse_discard_all_cards_in_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DISCARD_ALL_CARDS_IN_HAND_RE`, read as the "Discard your hand" clause
    `parse_clause_effect` already reads."""
    if "cards in your hand" not in clause.lower():
        return None
    if _DISCARD_ALL_CARDS_IN_HAND_RE.fullmatch(collapsed(clause.strip())) is None:
        return None
    return _parse_mixed_clause("Discard your hand", for_spell=for_spell)


@MIXED_CLAUSE.rung("s4", for_spell=FORWARD)
def _parse_draw_the_difference_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_DRAW_THE_DIFFERENCE_RE`, on a triggered ability whose intervening if
    is `_FEWER_THAN_N_CARDS_IN_HAND_RE`: its controller draws N minus the
    cards in their hand now. Any other antecedent draws nothing."""
    if for_spell or _DRAW_THE_DIFFERENCE_RE.fullmatch(collapsed(clause.strip())) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        condition = getattr(stack_object.ability, "intervening_if", None) or ""
        match = _FEWER_THAN_N_CARDS_IN_HAND_RE.fullmatch(condition.strip().rstrip("."))
        target = parse_count(match.group("n")) if match is not None else None
        if target is None:
            return
        player = game.controller_of(stack_object)
        difference = target - len(player.hand)
        if difference > 0:
            game.draw_cards(player.username, difference)

    return effect


#: "The next time they would draw a card this turn, instead they exile the
#: top card of their library." - Urabrask, Heretic Praetor's own second
#: trigger. "They" is CR 607.1's own anaphora back to the specific opponent
#: whose upkeep condition just fired, read off `AbilityOnStack.event.player`
#: exactly the way `_parse_they_gain_or_lose_life_clause` already reads
#: Sheoldred, the Apocalypse's own "they lose 2 life" - never the resolving
#: ability's controller.
#:
#: CR 614.1a's "next time ... would ..., instead ..." shape does not run
#: anything when the *trigger* resolves - it installs a one-shot replacement
#: (`Game.create_next_time_draw_replacement`) that a later draw event
#: consumes, the same division `_prevent_next_damage_from_target` already
#: draws for CR 615.8's identically-shaped damage shield. "your"/"that
#: player" are read too, on the same "target the mechanic" grounds the
#: widened `_PLAY_PERMISSION_RE` above already argues for third-person
#: permission sentences - only Urabrask's own "they"/"their" is proven here.
_NEXT_TIME_WOULD_DRAW_EXILE_TOP_RE = re.compile(
    r"^the next time (?:they|you|that player) would draw a card this turn, "
    r"instead (?:they|you|that player) exiles? the top card of "
    r"(?:their|your|that player'?s) library\.?$",
    re.IGNORECASE,
)


def _parse_next_time_draw_replacement_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_NEXT_TIME_WOULD_DRAW_EXILE_TOP_RE`'s first sentence, paired with the
    "They may play it this turn." permission that gives the exiled card
    anywhere to go (CR 601.3) - read together for the same reason
    `_parse_exile_then_play_permission_pair` reads its own pair together: the
    permission's pronoun has no meaning without the exile clause that names
    what "it" is.

    Ability-only: needs `AbilityOnStack.event.player` to resolve "they"
    against (CR 607.1), which a resolving spell has no equivalent of.
    """
    if for_spell:
        return None
    if _NEXT_TIME_WOULD_DRAW_EXILE_TOP_RE.fullmatch(first.strip()) is None:
        return None
    permission = _PLAY_PERMISSION_RE.fullmatch(second.strip())
    if permission is None:
        return None
    if _permission_duration(permission) is not PermissionDuration.THIS_TURN:
        # `NextTimeDrawReplacement` grants only a this-turn permission.
        return None
    if permission.group("subject").lower() in _PLURAL_PERMISSION_SUBJECTS:
        # One card exiled; the permission's pronoun must be singular.
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.player is None:
            return
        game.create_next_time_draw_replacement(
            NextTimeDrawReplacement(
                kind=DrawReplacementKind.EXILE_TOP_CARD,
                label=f"{ability.source_name}'s replacement effect",
                controller=game.controller_of(ability).username,
                affected=event.player,
                grants_play_permission=True,
                action=action,
                pays_mana_cost=not free,
            )
        )

    return effect


#: "target player discards <count> cards" - Go Blank's own first clause, and
#: P2's general vehicle: a plain CR 701.9a discard with no chooser override,
#: so CR 701.9b's default (the discarding player themselves) is left alone.
_TARGET_PLAYER_DISCARDS_RE = re.compile(
    r"^target player discards "
    rf"(?P<count>{COUNT}) cards?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_player_discards_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Target player discards N cards." (CR 701.9a), CR 701.9b's default
    chooser untouched - unlike Thoughtseize's own discard
    (`_merge_reveal_hand_choose_discard_clauses`), where "you choose" overrides
    it.

    A hand with fewer than N cards is not a rules violation the way CR
    119.4's life payment floor is: the player simply discards their whole
    hand, one at a time, which is why `needed` is capped at the hand's own
    size before ever asking `CHOOSE_CARDS` for it.
    """
    match = _TARGET_PLAYER_DISCARDS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
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
                    prompt=f"discard {needed} card(s)",
                    source=source,
                    amount=needed,
                    cards=tuple(state.id for state in target.hand),
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in target.hand}
            game.discard_cards(
                target.username, [by_id[card_id] for card_id in chosen_ids], source=source
            )

    return effect


#: "That player discards a card for each poison counter they have." - Whispering
#: Specter's reflexive consequence. "That player" is CR 607.1 anaphora back to
#: the player the triggering event named (the one dealt combat damage), and "they
#: have" is the same player, so the count is read on *them* (CR 122.1: counters
#: on a player), once, as the clause applies (CR 608.2h) - before any card goes.
_THAT_PLAYER_DISCARDS_PER_COUNTER_RE = re.compile(
    rf"^that player discards (?P<n>{COUNT}) cards? for each (?P<each>.+?)\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_that_player_discards_per_counter_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYER_DISCARDS_PER_COUNTER_RE`'s shape (ability-only: a spell
    has no triggering event), or `None`."""
    if for_spell:
        return None
    match = _THAT_PLAYER_DISCARDS_PER_COUNTER_RE.fullmatch(clause.strip())
    if match is None:
        return None
    per_unit = parse_count(match.group("n"))
    counted = player_counter_count(match.group("each"), anaphoric=True)
    if per_unit is None or counted is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        event = getattr(stack_object, "event", None)
        username = None if event is None else event.player or event.subject_controller
        if username is None:
            return
        player = game.player(username)
        needed = min(per_unit * counted(game, username), len(player.hand))
        if needed <= 0:
            return
        source = stack_object.source_name  # type: ignore[union-attr]
        _discard_cards(game, player, needed, source, source_id=source_id_of(stack_object))

    return effect


#: "Each opponent discards N cards."/"Each player discards N cards." with
#: nothing after it - CR 102.2's "each opponent"/"each player", CR 701.9a's
#: plain discard, CR 701.9b's default chooser (the discarding player
#: themselves) left untouched, exactly `_TARGET_PLAYER_DISCARDS_RE`'s own
#: shape over "each opponent"/"each player" instead of one chosen target.
#: The shortfall-consequence siblings just above
#: (`_EACH_OPPONENT_DISCARDS_THEN_DRAW_PER_SHORTFALL_RE` and its "loses
#: life" twin) only ever match a *two*-sentence instruction naming a
#: shortfall - Nicol Bolas, the Ravager's own "When Nicol Bolas enters,
#: each opponent discards a card." has no second sentence at all, so it
#: fell through every one of them silently until this shape was added.
#: Liliana of the Veil's `+1` ("Each player discards a card.") is the
#: "each player" off-set proof - a real, non-pool printing of the identical
#: shape as a loyalty ability's own effect rather than an ETB trigger's,
#: which also confirms the clause reader works from `parse_mixed_effect`'s
#: shared per-clause dispatch regardless of which kind of ability calls it.
_EACH_OPPONENT_DISCARDS_RE = re.compile(
    rf"^each (?P<who>opponent|player) discards {count_pattern('count')} cards?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_each_opponent_discards_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_EACH_OPPONENT_DISCARDS_RE`'s shape - CR 701.9a/701.9b/CR 102.2, no
    target at all (an opponent is not a target, CR 115.1) and no shortfall
    consequence, so each opponent - or, for "each player", the controller
    too - (CR 101.4 APNAP order, `_players_in_apnap_order`) simply discards
    their own choice of `count` cards, CR 609.3's "as much as possible" for
    a shorter hand.
    """
    match = _EACH_OPPONENT_DISCARDS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None or count < 1:
        return None
    opponents_only = match.group("who").lower() == "opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        controller_username = game.controller_of(stack_object).username
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller_username:
                continue
            needed = min(count, len(player.hand))
            if needed <= 0:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"discard {needed} card(s)",
                    source=source,
                    amount=needed,
                    cards=tuple(state.id for state in player.hand),
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in player.hand}
            game.discard_cards(
                player.username, [by_id[card_id] for card_id in chosen_ids], source=source
            )

    return effect


#: "Target player draws N cards." (Ancestral Vision) - CR 121.1's plain draw,
#: aimed at a chosen player rather than the caster (`_DRAW_RE`'s "you" or
#: implicit-"you" shapes never reach a resolving *target*). The same
#: sentence shape as `_TARGET_PLAYER_DISCARDS_RE`, one CR 701.9a verb swapped
#: for CR 121.1's.
_TARGET_PLAYER_DRAWS_RE = re.compile(
    r"^target player draws "
    rf"(?P<count>{COUNT}) cards?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_player_draws_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TARGET_PLAYER_DRAWS_RE`'s shape, or `None` if this is not it."""
    match = _TARGET_PLAYER_DRAWS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.draw_cards(target.username, count)

    return effect


#: "Two target players each draw a card." (Gleaming Splendor) - CR 115.6's
#: own exact-count target profile ("two target players", not "up to two"),
#: each drawing independently: CR 121.1's ordinary draw, repeated once per
#: legal target the same count-agnostic way `_targets_understood` already
#: lets destroy/exile/tap/untap/return/put-counters repeat (see its own
#: docstring) - draw is exactly as count-agnostic a verb as those.
_N_TARGET_PLAYERS_EACH_DRAW_RE = re.compile(
    rf"^{count_pattern('players')} target players each draws? {count_pattern('count')} cards?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_n_target_players_each_draw_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_N_TARGET_PLAYERS_EACH_DRAW_RE`'s shape, or `None` if this is not it."""
    match = _N_TARGET_PLAYERS_EACH_DRAW_RE.fullmatch(clause.strip())
    if match is None:
        return None
    phrase = f"{match.group('players')} target players"
    if not _targets_understood(phrase, allow_player_targets=True, count_agnostic=True):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.draw_cards(target.username, count)

    return effect


#: "Target player draws `<n>` cards and loses `<m>` life." - Ancestral
#: Craving's and Blood Pact's own whole shape: one compound predicate, one
#: subject, not two independent instructions. `_CLAUSE_SEPARATOR`'s bare
#: "and" splits this into "target player draws N cards" and a subject-less
#: "loses M life" that `_parse_optional_player_clause`'s own fallback then
#: applies to the resolving spell's *controller* rather than the target it
#: was actually about (the caster, not the target, lost the life) - read
#: whole, ahead of that split, for the identical reason `_parse_mixed_
#: clauses`'s other whole-text entries are. General across any card sharing
#: this exact template - real cards this shape covers include Blood Bairn's
#: own activated ability half and Debt to the Deathless's smaller siblings -
#: not keyed to Ancestral Craving's name.
_TARGET_PLAYER_DRAWS_AND_LOSES_LIFE_RE = re.compile(
    rf"^target player draws (?P<draw_n>{COUNT}) cards? and loses (?P<life>{COUNT}) life\.?$",
    re.IGNORECASE,
)


def _parse_target_player_draws_and_loses_life_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_DRAWS_AND_LOSES_LIFE_RE`'s shape, or `None`."""
    match = _TARGET_PLAYER_DRAWS_AND_LOSES_LIFE_RE.fullmatch(collapsed(clause))
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    draw_count = parse_count(match.group("draw_n"))
    life_loss = parse_count(match.group("life"))
    if draw_count is None or life_loss is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.draw_cards(target.username, draw_count)
                game.lose_life(target, life_loss)

    return effect


#: "Each player may discard their hand and draw seven cards." (Arc of
#: Fortune) - CR 601.2/608.2d's per-player `MAY` question, asked of every
#: player still in the game, in APNAP order (`Game.players`'s own order,
#: turn order starting with the active player - the same order every other
#: "each player" effect in this module already iterates).
_EACH_PLAYER_MAY_DISCARD_HAND_DRAW_RE = re.compile(
    rf"^each player may discard (?:their|your|his or her) hand and draw (?P<count>{COUNT}) "
    rf"cards?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s25", for_spell=FORWARD)
def _parse_each_player_may_discard_hand_and_draw_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_MAY_DISCARD_HAND_DRAW_RE`'s shape - see its own
    docstring. General across any printed count, not fixed at seven."""
    match = _EACH_PLAYER_MAY_DISCARD_HAND_DRAW_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        for player in list(game.players):
            if not game.is_in_game(player.username):
                continue
            if game.may(
                player,
                f"discard your hand and draw {count} cards",
                source=source,
                source_id=source_id_of(stack_object),
            ):
                hand = list(player.hand)
                if hand:
                    game.discard_cards(player.username, hand, source=source)
                game.draw_cards(player.username, count)

    return effect  # type: ignore[return-value]


#: "Each opponent discards their hand." (Myojin of Night's Reach) and "Each
#: player discards their hand." - CR 701.9a's discard of the whole hand, as
#: one instruction per affected player in APNAP order (CR 101.4). No choice is
#: asked: a hand discarded whole has nothing to choose (CR 701.9b).
_EACH_PLAYER_DISCARDS_HAND_RE = re.compile(
    r"^each (?P<who>opponent|player) discards (?:their|his or her) hand\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s25", for_spell=FORWARD)
def _parse_each_player_discards_hand_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_EACH_PLAYER_DISCARDS_HAND_RE`'s shape."""
    match = _EACH_PLAYER_DISCARDS_HAND_RE.fullmatch(text.strip())
    if match is None:
        return None
    opponents_only = match.group("who").lower() == "opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            hand = list(player.hand)
            if hand:
                game.discard_cards(player.username, hand, source=source)

    return effect  # type: ignore[return-value]


#: "Draw a card if you control a `<color>` permanent[ other than `<self>`]."
#: - Ral, Monsoon Mage's own −2, second sentence. A mandatory, board-state-
#: gated draw (CR 121.1), not CR 608.2d's "you may" - the condition is
#: checked once, as the ability resolves, not re-checked afterward.
#: "permanent" is not one of CR 205.2a's card types (`_quality_matcher`'s
#: own vocabulary is built for library-search qualities, which always name a
#: *card* type), so this reads the color alone rather than trying to force
#: "permanent" through that matcher.
_DRAW_IF_YOU_CONTROL_COLOR_PERMANENT_RE = re.compile(
    rf"^draw (?:a card|(?P<count>{COUNT}) cards) if you control (?:a|an) "
    r"(?P<color>white|blue|black|red|green) permanent"
    r"(?: other than (?P<exclude>.+))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35")
def _parse_draw_if_you_control_color_permanent_clause(clause: str) -> TargetedClause | None:
    """`_DRAW_IF_YOU_CONTROL_COLOR_PERMANENT_RE`'s shape, or `None`."""
    match = _DRAW_IF_YOU_CONTROL_COLOR_PERMANENT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    color = _HAND_EXILE_COLOR_WORDS.get(match.group("color").lower())
    if color is None:
        return None
    count_text = match.group("count")
    if count_text is None:
        count = 1
    else:
        count = parse_count(count_text)
        if count is None:
            return None
    excludes_self = match.group("exclude") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        player = game.controller_of(stack_object)
        source = stack_object.source(game)
        # CR 613.5 / CR 613.1e: colour is layer 5's answer, not the printed
        # mana cost's - a permanent an effect has made red counts, and one a
        # "becomes colorless" effect has drained does not.
        qualifies = bool(
            computed_permanents(
                game,
                (
                    state
                    for state in game.permanents_controlled_by(player.username)
                    if not (excludes_self and source is not None and state.id == source.id)
                ),
                lambda chars: color in chars.colors,
            )
        )
        if qualifies:
            game.draw_cards(player.username, count)

    return effect


#: "You may have target opponent draw a card. If you do, copy that spell.
#: You may choose new targets for the copy." - Alania, Divergent Storm's own
#: cast trigger, read as one CR 608.2c instruction chain: CR 707.1's copy is
#: conditional (CR 118.12's "if you do") on the draw actually happening, and
#: "that spell" is CR 607.1 anaphora back to the very spell this ability's
#: own `TriggerEvent.CAST_SPELL` watched (`ability.event.subject_id`), not a
#: target this ability announces itself.
_TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE = re.compile(
    r"^you may have target opponent draw a card\. if you do, copy that spell\. "
    r"you may choose new targets for the copy\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_target_opponent_draw_then_copy_that_spell_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE`'s shape - Alania,
    Divergent Storm's whole cast trigger (CR 121.1's draw; CR 707.10's copy,
    via `Game.copy_spell`; CR 707.10c's retargeting, via `Game.
    offer_new_targets_for_copy`).
    """
    if _TARGET_OPPONENT_DRAW_THEN_COPY_THAT_SPELL_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        opponent = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if opponent is None:
            return
        if not game.may(
            game.player(ability.controller),
            "have target opponent draw a card",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.draw_cards(opponent.username, 1)

        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        copy = game.copy_spell(spell, controller=ability.controller)
        game.offer_new_targets_for_copy(
            copy,
            ability.controller,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


#: "draw `<n>` cards. At the beginning of your next upkeep, discard `<n>`
#: cards at random." - Casey Jones, Vigilante's own enters-the-battlefield
#: trigger (TMT). The draw half is an ordinary plain player clause
#: `parse_mixed_effect` already reads alone; only the delayed discard needs a
#: reader, but the two are read together here (rather than leaving the draw
#: to the ordinary per-clause path and adding only the delayed half to
#: `_parse_delayed_single_clause`) because both halves share one printed
#: count and this way needs no anaphora at all - a plain, complete CR 608.2c
#: instruction pair, matched whole for symmetry with every other TMT T7
#: reader in this section.
_DRAW_THEN_DELAYED_DISCARD_AT_RANDOM_RE = re.compile(
    rf"^draw (?P<draw_n>{COUNT}) cards?\.\s*"
    rf"at the beginning of your next upkeep, discard (?P<discard_n>{COUNT}) cards? at random\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_draw_then_delayed_discard_at_random_clause(text: str) -> AbilityEffect | None:
    """`_DRAW_THEN_DELAYED_DISCARD_AT_RANDOM_RE`'s shape, or `None`."""
    match = _DRAW_THEN_DELAYED_DISCARD_AT_RANDOM_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    draw_count = parse_count(match.group("draw_n"))
    discard_count = parse_count(match.group("discard_n"))
    if draw_count is None or discard_count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        game.draw_cards(controller.username, draw_count)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    f"At the beginning of your next upkeep, discard {discard_count} "
                    "cards at random."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.UPKEEP,
                controller=controller.username,
                source_id=ability.source_id,
                source_name=ability.source_name,
                only_when_active=controller.username,
                effect=DiscardCardsAtRandomForController(count=discard_count),
            )
        )

    return effect


#: "Each opponent discards `<n>` cards. For each opponent who didn't discard
#: `<n>` nonland cards this way, you draw a card." - Garruk, Veiled Butcher's
#: own `-3`. CR 701.9b's discard is each opponent's own choice, and CR 609.3
#: still lets a hand shorter than `<n>` discard fewer than `<n>` cards - both
#: of which are exactly why "didn't discard `<n>` nonland cards" is a real,
#: per-opponent shortfall rather than a fixed penalty: an opponent with two
#: lands and a Bolt discards Bolt plus one land and still falls one nonland
#: short, the same as an opponent with only one card in hand.
def _each_opponent_discards_and_count_shortfalls(
    game: "Game",
    stack_object: "StackObject",
    *,
    discard_n: int,
    nonland_n: int,
    source_name: str,
) -> list[Player]:
    """CR 701.9b: each opponent discards `discard_n` cards of their own
    choice (CR 609.3: a shorter hand discards what it has), then reports
    which opponents fell short of `nonland_n` nonland cards among what they
    actually discarded - the shared half of Garruk, Veiled Butcher's own
    `-3` ("For each opponent who didn't discard two nonland cards this way,
    you draw a card.") and Kroxa, Titan of Death's Hunger's identically
    shaped antecedent ("... then each opponent who didn't discard a nonland
    card this way loses 3 life."). Only the *consequence* differs between
    the two - a controller-side count-of-shortfalls draw for Garruk, a
    per-shortfall-player life loss for Kroxa - so it is each caller's own
    small wrapper, not this shared antecedent, that reads differently.

    Every opponent discards before any shortfall is judged: nothing any one
    opponent sees changes what another may discard, so there is no CR 101.4
    ordering question here, only CR 608.2c's "this way" scoping the second
    half to what the first actually put into a graveyard.
    """
    controller_username = game.controller_of(stack_object).username
    shortfall_players: list[Player] = []
    for player in _players_in_apnap_order(game):
        if player.username == controller_username:
            continue
        hand = list(player.hand)
        amount = min(discard_n, len(hand))
        if amount <= 0:
            shortfall_players.append(player)
            continue
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {amount} card(s) to discard",
                source=source_name,
                source_id=source_id_of(stack_object),
                amount=amount,
                cards=tuple(state.id for state in reversed(hand)),
            )
        )
        by_id = {state.id: state for state in hand}
        discarded = [by_id[card_id] for card_id in chosen_ids]
        game.discard_cards(player.username, discarded, source=source_name)
        nonlands = sum(1 for state in discarded if not state.card.is_land)
        if nonlands < nonland_n:
            shortfall_players.append(player)
    return shortfall_players


_EACH_OPPONENT_DISCARDS_THEN_DRAW_PER_SHORTFALL_RE = re.compile(
    rf"^each opponent discards {count_pattern('discard_n')} cards?\.\s*"
    rf"for each opponent who didn'?t discard {count_pattern('nonland_n')} nonland cards? "
    r"this way, you draw a card\.?$",
    re.IGNORECASE,
)


def _parse_each_opponent_discards_then_draw_per_shortfall_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_OPPONENT_DISCARDS_THEN_DRAW_PER_SHORTFALL_RE`'s shape - Garruk,
    Veiled Butcher's own `-3`. Read whole, the same "this way" reason every
    other two-sentence rider in this module is: the second sentence counts a
    fact about the first sentence's own outcome, one draw per opponent who
    fell short, not an independent instruction.
    """
    match = _EACH_OPPONENT_DISCARDS_THEN_DRAW_PER_SHORTFALL_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    discard_n = parse_count(match.group("discard_n"))
    nonland_n = parse_count(match.group("nonland_n"))
    if discard_n is None or discard_n < 1 or nonland_n is None or nonland_n < 1:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller_username = game.controller_of(stack_object).username
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        shortfalls = _each_opponent_discards_and_count_shortfalls(
            game,
            stack_object,
            discard_n=discard_n,
            nonland_n=nonland_n,
            source_name=source_name,
        )
        if shortfalls:
            game.draw_cards(game.player(controller_username), len(shortfalls))

    return effect


#: "Each opponent discards `<n>` card(s), then each opponent who didn't
#: discard `<n>` nonland card(s) this way loses `<m>` life." - Kroxa, Titan
#: of Death's Hunger's own enters-or-attacks trigger. The same antecedent as
#: Garruk, Veiled Butcher's `-3` (`_each_opponent_discards_and_count_
#: shortfalls`), joined with "then" rather than a new sentence, and the
#: consequence lands on each shortfall *opponent themselves* ("loses N
#: life") rather than on the ability's controller.
_EACH_OPPONENT_DISCARDS_THEN_SHORTFALL_LOSES_LIFE_RE = re.compile(
    rf"^each opponent discards {count_pattern('discard_n')} cards?,?\s*then each opponent who "
    rf"did(?:n'?t|\s+not) discard {count_pattern('nonland_n')} nonland cards? this way loses "
    rf"{count_pattern('life_n')} life\.?$",
    re.IGNORECASE,
)


def _parse_each_opponent_discards_then_shortfall_loses_life_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_OPPONENT_DISCARDS_THEN_SHORTFALL_LOSES_LIFE_RE`'s shape."""
    match = _EACH_OPPONENT_DISCARDS_THEN_SHORTFALL_LOSES_LIFE_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    discard_n = parse_count(match.group("discard_n"))
    nonland_n = parse_count(match.group("nonland_n"))
    life_n = parse_count(match.group("life_n"))
    if (
        discard_n is None
        or discard_n < 1
        or nonland_n is None
        or nonland_n < 1
        or life_n is None
        or life_n < 1
    ):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        shortfalls = _each_opponent_discards_and_count_shortfalls(
            game,
            stack_object,
            discard_n=discard_n,
            nonland_n=nonland_n,
            source_name=source_name,
        )
        for player in shortfalls:
            game.lose_life(player, life_n)

    return effect


# --------------------------------------------------------------------------
# "Put a permanent card from your hand onto the battlefield." (CR 110.2a)
# --------------------------------------------------------------------------
#
# Kona, Rescue Beastie's own *survival* trigger, wrapped in CR 608.2d's plain
# "you may". Not a cast at all, so no "when you cast"
# ability fires and no mana is paid - `Game.put_onto_battlefield`'s own
# docstring is the authority for both. Which card is CR 608.2d's choice, made
# by the ability's controller among their own hand.

#: "Put a permanent card from your hand onto the battlefield." (Kona, Rescue
#: Beastie) and "Put up to two creature cards from your hand onto the
#: battlefield." (Tooth and Nail's second mode) - one shape, because the second
#: is the first with a count in front of it and the noun pluralised. CR 115.6's
#: "up to N" wording is the same "nought to N" the targeting parser reads, and
#: nothing about the verb changes with the count: it repeats itself once per
#: card chosen, so a hand short of N puts as many as it can (CR 609.3: an
#: effect "does as much as it can"). "Put any number of creature cards from
#: your hand onto the battlefield." (Ghalta, Stampede Tyrant; Last March of
#: the Ents) is the same shape with CR 107.1c's "any number" as the count:
#: every card that qualifies, or none.
_PUT_PERMANENT_CARD_FROM_HAND_RE = re.compile(
    r"^(?P<may>you may )?put (?:a|an|up to (?P<count>[\w-]+)|(?P<any>any number of)) "
    r"(?P<group>[a-z]+) cards?"
    # ecl-T8: Meek Attack's own "a creature card with total power and
    # toughness 5 or less" - an additional filter on top of whatever
    # `_parse_card_group_qualifier` already reads for the bare group word.
    r"(?: with total power and toughness (?P<total_pt>\d+) or less)? "
    r"from your hand onto the battlefield(?P<tapped> tapped)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s6", for_spell=False)
@SPELL_TEXT.rung("s4", for_spell=True)
@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_put_permanent_card_from_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PUT_PERMANENT_CARD_FROM_HAND_RE`'s shape - Kona, Rescue Beastie, and
    Tooth and Nail's "Put up to two creature cards from your hand onto the
    battlefield."

    The group is read by `_parse_card_group_qualifier`, so "permanent card"
    (CR 110.4a's group) and any single CR 205.2a card type both work, off the
    card's own printed characteristics (CR 400.7: a card in a hand has
    nothing else). A hand with no legal candidate is never asked at all
    (CR 608.2d: "the player can't choose an option that's illegal or
    impossible"), and a hand holding fewer than the stated count is asked for
    as many as it holds - CR 609.3's "does as much as it can", the same floor
    every other counted instruction in this file applies.
    """
    match = _PUT_PERMANENT_CARD_FROM_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    group_predicate = _parse_card_group_qualifier(match.group("group"))
    if group_predicate is None:
        return None
    total_pt_ceiling = int(match.group("total_pt")) if match.group("total_pt") else None

    def predicate(state: CardState) -> bool:
        if not group_predicate(state):
            return False
        if total_pt_ceiling is None:
            return True
        # A creature whose power or toughness is `*` or otherwise
        # non-numeric (CR 613.4) cannot be verified against a fixed ceiling
        # off the battlefield - excluded rather than guessed at.
        return (
            state.power is not None
            and state.toughness is not None
            and state.power + state.toughness <= total_pt_ceiling
        )

    amount = 1
    if match.group("count"):
        parsed = parse_count(match.group("count"))
        if parsed is None:
            # "up to X creature cards" (CR 107.3a's X, unsubstituted) or a word
            # that is not a count - fail closed rather than guess.
            return None
        amount = parsed
    any_number = match.group("any") is not None
    # The printed group word, so the question names what the card says
    # ("a land card", "a creature card"), not a generic "permanent card".
    group = match.group("group").lower()
    optional = match.group("may") is not None
    tapped = match.group("tapped") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        candidates = [state for state in list(controller.hand) if predicate(state)]
        if not candidates:
            return
        if any_number:
            # CR 107.1c: one question, zero to every candidate - no "may"
            # gate in front of it, since choosing none already declines.
            chosen_any = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose any number of {group} cards to put onto the battlefield",
                    source=source_name,
                    amount=len(candidates),
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                    source_id=source_id_of(stack_object),
                )
            )
            by_any_id = {state.id: state for state in candidates}
            # CR 603.6a: one instruction, one entering event.
            with game.entering_together():
                for card_id in chosen_any:
                    game.put_onto_battlefield(
                        by_any_id[card_id], controller.username, tapped=tapped
                    )
            return
        if optional and not game.may(
            controller,
            f"put {with_indefinite_article(group)} card from your hand onto the battlefield",
            source=source_name,
            source_id=source_id_of(stack_object),
        ):
            return
        wanted = min(amount, len(candidates))
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose {wanted} {group} card(s) to put onto the battlefield",
                source=source_name,
                amount=wanted,
                cards=tuple(state.id for state in candidates),
                source_id=source_id_of(stack_object),
            )
        )
        by_id = {state.id: state for state in candidates}
        with game.entering_together():  # CR 603.6a
            for card_id in chosen_ids:
                state = by_id.get(card_id)
                if state is not None:
                    game.put_onto_battlefield(state, controller.username, tapped=tapped)

    return effect


# --------------------------------------------------------------------------
# "Draw N cards. Then discard M cards unless you discard a <quality> card."
# --------------------------------------------------------------------------
#
# Winternight Stories. CR 118.12a's own reading of "unless" - "[Do
# something] unless [a player does something else]" means "[a player] may [do
# something else]. If [that player] doesn't, [effect]" - applied to a
# discard: the player may discard one card of the named quality, and only if
# they do not does the larger discard happen.

_DRAW_THEN_DISCARD_UNLESS_RE = re.compile(
    rf"^draw (?P<draw>{COUNT}) cards?\.\s*then discard (?P<n>{COUNT}) cards? "
    r"unless you discard an? (?P<group>[a-z]+) card\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _draw_then_discard_unless_runner(
    draw: int, penalty: int, predicate: "Callable[[CardState], bool]", quality: str
) -> "Callable[[Game, Player, str, UUID | None], None]":
    """The shared half of `_parse_draw_then_discard_unless` and
    `_parse_draw_then_discard_unless_ability`: everything after the regex
    has matched and the count/predicate have been read, parametrized on
    `controller`/`source_name`/`source_id` rather than on a resolving
    `CardState` (a spell) or `AbilityOnStack` (an activated or triggered
    ability) directly - CR 118.12a's "unless" reading does not care which
    kind of object is resolving, only `Game.may`/`Game.ask`'s own callers do.

    The "unless" branch is only offered when a card of the named quality is
    actually in hand (CR 608.2d: an impossible option cannot be chosen), and
    the choice of *which* such card is the discarding player's own
    (CR 701.9b). Declining, or having none, falls through to the plain
    discard `_discard_cards` already performs.
    """

    def run(game: "Game", controller: "Player", source_name: str, source_id: "UUID | None") -> None:
        game.draw_cards(controller.username, draw)
        candidates = [state for state in list(controller.hand) if predicate(state)]
        if candidates and game.may(
            controller,
            f"discard {with_indefinite_article(f'{quality} card')}",
            source=source_name,
            source_id=source_id,
        ):
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose {with_indefinite_article(f'{quality} card')} to discard",
                    source=source_name,
                    source_id=source_id,
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            discarding = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            if discarding:
                game.discard_cards(controller.username, discarding, source=source_name)
                return
        _discard_cards(game, controller, penalty, source_name, source_id=source_id)

    return run


def _parse_draw_then_discard_unless_shape(
    text: str,
) -> "Callable[[Game, Player, str, UUID | None], None] | None":
    """`_DRAW_THEN_DISCARD_UNLESS_RE`'s shape read into a `_draw_then_
    discard_unless_runner`, or `None` - shared by the spell and ability
    dispatchers below so neither has to repeat the regex or the predicate
    read."""
    match = _DRAW_THEN_DISCARD_UNLESS_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    draw = parse_count(match.group("draw"))
    penalty = parse_count(match.group("n"))
    if draw is None or penalty is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("group"))
    if predicate is None:
        return None
    quality = match.group("group").lower()
    return _draw_then_discard_unless_runner(draw, penalty, predicate, quality)


@SPELL_TEXT.rung("s22")
def _parse_draw_then_discard_unless(text: str) -> Effect | None:
    """`_DRAW_THEN_DISCARD_UNLESS_RE`'s shape on a resolving spell -
    Winternight Stories, Mystic Meditation, Thirst for Identity."""
    run = _parse_draw_then_discard_unless_shape(text)
    if run is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        run(game, game.controller_of(spell), spell.name, source_id_of(spell))

    return effect


@ABILITY_TEXT.rung("s22")
def _parse_draw_then_discard_unless_ability(text: str) -> AbilityEffect | None:
    """`_DRAW_THEN_DISCARD_UNLESS_RE`'s shape on an activated or triggered
    ability instead of a spell - Invasion of New Phyrexia // Teferi Akosa of
    Zhalfir's own "+1: Draw two cards. Then discard two cards unless you
    discard a creature card." (CR 606.2: a loyalty ability is an activated
    ability). Nothing about the regex or the predicate it reads is
    spell-specific, so this is the same shape read for `ability.controller`/
    `ability.source_name` instead of a resolving `CardState`'s own."""
    run = _parse_draw_then_discard_unless_shape(text)
    if run is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        run(game, game.player(ability.controller), ability.source_name, source_id_of(ability))

    return effect


#: "Draw cards equal to the sacrificed creature's power, then discard a
#: card." - Tom, Bert, and William's own "{1}, Sacrifice another creature:"
#: ability. The identical CR 602.2b timing `_CONDITIONAL_TOKEN_COUNT_ON_
#: SACRIFICED_RE` above already documents: the creature is gone (CR 400.7)
#: before this ability is even on the stack, so its power is the printed one
#: on `AbilityOnStack.cost_sacrificed_card_ids`'s own recorded card, never a
#: live `Game.power_of` (there is no permanent left to compute layers for).
_DRAW_EQUAL_TO_SACRIFICED_CREATURE_POWER_THEN_DISCARD_RE = re.compile(
    rf"^draw cards equal to the sacrificed creature'?s power,?\s*"
    rf"then discard {count_pattern('n')} cards?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_draw_equal_to_sacrificed_creature_power_then_discard_clause(
    text: str,
) -> AbilityEffect | None:
    """`_DRAW_EQUAL_TO_SACRIFICED_CREATURE_POWER_THEN_DISCARD_RE`'s shape.

    "The sacrificed creature" (singular) reads every card this activation's
    own cost sacrificed - always exactly one for "Sacrifice another
    creature", but summed rather than pinned to `[0]` so a future cost
    sacrificing more than one still reads correctly. A `*` power CDA (CR
    208.2) has no printed number once the object is gone and contributes
    nothing, the same "unreadable counts as zero, not a crash" `_parse_
    conditional_token_count_on_sacrificed` already applies to its own
    printed-power read.
    """
    match = _DRAW_EQUAL_TO_SACRIFICED_CREATURE_POWER_THEN_DISCARD_RE.fullmatch(text.strip())
    if match is None:
        return None
    discard_amount = parse_count(match.group("n"))
    if discard_amount is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        total_power = _cost_sacrificed_stat_total(game, ability, "power")
        if total_power > 0:
            game.draw_cards(controller.username, total_power)
        _discard_cards(
            game,
            controller,
            discard_amount,
            ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


#: "draw a card if her power is 4 or greater." (Viv Vision, Teen
#: Synthezoid's attack trigger); "draw a card if its power is 3 or greater.
#: Otherwise, put two +1/+1 counters on it." (Tribute to the World Tree) - a
#: draw gated on one creature's power as the ability resolves (CR 608.2h),
#: with an optional "Otherwise" instruction for the false case. A legend's
#: own pronoun ("his"/"her") and "this creature's" name the source; "its"
#: names the creature the trigger's event is about (CR 603.2), which for a
#: self trigger is the source anyway.
_DRAW_IF_POWER_AT_LEAST_RE = re.compile(
    rf"^draw (?P<n>{COUNT}) cards? if (?P<whose>its|his|her|this (?:creature|permanent)'s) "
    r"power is (?P<threshold>\d+) or greater\.?(?:\s*otherwise,\s*(?P<otherwise>.+))?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_draw_if_power_at_least(text: str) -> AbilityEffect | None:
    """`_DRAW_IF_POWER_AT_LEAST_RE`'s shape, or `None`."""
    match = _DRAW_IF_POWER_AT_LEAST_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if not count:
        return None
    threshold = int(match.group("threshold"))
    otherwise_text = match.group("otherwise")
    otherwise = parse_mixed_effect(otherwise_text) if otherwise_text else None
    if otherwise_text and otherwise is None:
        return None
    reads_event_subject = match.group("whose").lower() == "its"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        subject = None
        if reads_event_subject and ability.event is not None and ability.event.subject_id:
            subject = game.find_by_id(ability.event.subject_id)
        if subject is None:
            subject = ability.source_or_last_known(game)
        if _source_characteristic(game, subject, "power") >= threshold:
            game.draw_cards(game.controller_of(ability).username, count)
        elif otherwise is not None:
            otherwise(game, ability)

    return effect


#: "You may put a creature card and/or a land card from your hand onto the
#: battlefield." - Michelangelo, Improviser's own combat-damage trigger. Two
#: independent CR 110.4a permanent-card groups joined by "and/or" (CR 608.2c's
#: plain English: do one, the other, both, or neither), unlike `_PUT_
#: PERMANENT_CARD_FROM_HAND_RE`'s single group ("a permanent card", Kona,
#: Rescue Beastie) - a card that could satisfy both named groups is asked
#: about at most once, since the first offer that takes it removes it from
#: the hand the second offer reads.
_PUT_TWO_CARD_GROUPS_AND_OR_FROM_HAND_RE = re.compile(
    r"^you may put an? (?P<first>[a-z]+) card and/or an? (?P<second>[a-z]+) card "
    r"from your hand onto the battlefield(?P<tapped> tapped)?\.?$",
    re.IGNORECASE,
)


def _parse_put_two_card_groups_and_or_from_hand_clause(text: str) -> AbilityEffect | None:
    """`_PUT_TWO_CARD_GROUPS_AND_OR_FROM_HAND_RE`'s shape.

    Each group is its own CR 608.2d question, asked and resolved in printed
    order (`_parse_card_group_qualifier`, the same reader Ilharg's own hand
    group and Kona's permanent-card group already use) - "and/or" never
    couples them into one joint choice, so a hand with only a land card in it
    is still asked (and can still answer yes to) the land half even though
    the creature half finds nothing to offer.
    """
    match = _PUT_TWO_CARD_GROUPS_AND_OR_FROM_HAND_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    first_predicate = _parse_card_group_qualifier(match.group("first"))
    second_predicate = _parse_card_group_qualifier(match.group("second"))
    if first_predicate is None or second_predicate is None:
        return None
    tapped = match.group("tapped") is not None
    first_word = match.group("first")
    second_word = match.group("second")

    def offer(
        game: "Game",
        controller: Player,
        source_name: str,
        source_id: UUID | None,
        predicate: Callable[[CardState], bool],
        word: str,
    ) -> None:
        candidates = [state for state in list(controller.hand) if predicate(state)]
        if not candidates:
            return
        if not game.may(
            controller,
            f"put a {word} card from your hand onto the battlefield",
            source=source_name,
            source_id=source_id,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose a {word} card to put onto the battlefield",
                source=source_name,
                source_id=source_id,
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        game.put_onto_battlefield(by_id[chosen_ids[0]], controller.username, tapped=tapped)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id = source_id_of(ability)
        offer(game, controller, ability.source_name, source_id, first_predicate, first_word)
        offer(game, controller, ability.source_name, source_id, second_predicate, second_word)

    return effect


#: "Discard a card, then draw a card." / "Draw a card, then [you may] discard a
#: card." followed by CR 603.12's reflexive "When you discard [a|an `<quality>`]
#: card this way, `<consequence>`." - Flamethrower Sonata, Glacial Dragonhunt,
#: Narset of the Ancient Way's -2. "This way" is CR 608.2c anaphora onto the
#: discard the first sentence performed, so the pair is read whole: the
#: reflexive ability exists only if the card actually discarded has the
#: quality (a land discarded to a "nonland" trigger creates nothing), and it
#: is a new object that announces its own targets as it goes on the stack
#: (CR 603.3d, `Game.create_reflexive_trigger`).
_LOOT_THEN_REFLEXIVE_DISCARD_RE = re.compile(
    r"^(?:(?P<discard_first>discard a card, then draw a card)"
    r"|draw a card, then (?P<may>you may )?discard a card)"
    r"\.\s*when you discard (?:a card|an? (?P<quality>[a-z, ]+?) card) this way,\s*"
    r"(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "damage equal to that card's mana value" - the discarded card's mana value
#: (CR 202.3), written into the reflexive ability's text as a number when it
#: is created, the way a cast X is (CR 107.3a), because the reflexive ability
#: is a new object and the discarded card is the only thing that remembers it.
_DAMAGE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE = re.compile(
    r"\bdamage equal to (?:that card'?s|its) mana value\b", re.IGNORECASE
)


def _loot_then_reflexive_discard_effect(
    text: str, *, for_spell: bool
) -> "Callable[[Game, StackObject], None] | None":
    """`_LOOT_THEN_REFLEXIVE_DISCARD_RE`'s shape for a spell or an ability."""
    whole = collapsed(_strip_non_effect_preamble(text))
    match = _LOOT_THEN_REFLEXIVE_DISCARD_RE.fullmatch(whole)
    if match is None:
        return None
    quality = match.group("quality")
    matches_quality = _nonland_or_typed_card_matcher(quality) if quality else None
    if quality and matches_quality is None:
        return None
    discard_first = match.group("discard_first") is not None
    optional = match.group("may") is not None
    consequence = match.group("consequence").strip()
    carries_mana_value = _DAMAGE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE.search(consequence) is not None

    def with_mana_value(value: int) -> str:
        return _DAMAGE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE.sub(f"{value} damage", consequence)

    if re.search(r"\bthat card\b|\bits mana value\b", with_mana_value(2), re.IGNORECASE):
        return None
    if reflexive_consequence_effect(with_mana_value(2) + ".") is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        discarded: list[CardState] = []
        if discard_first:
            discarded = _discard_cards(
                game, player, 1, source_name, source_id=str(source_id), exact=True
            )
            game.draw_cards(player, 1)
        else:
            game.draw_cards(player, 1)
            if optional and not game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt="discard a card",
                    source=source_name,
                    affirmative_is_legal=bool(player.hand),
                    source_id=str(source_id),
                )
            ):
                return
            discarded = _discard_cards(
                game, player, 1, source_name, source_id=str(source_id), exact=True
            )
        if not discarded or (matches_quality is not None and not matches_quality(discarded[0])):
            return
        value = int(discarded[0].mana_value)
        if carries_mana_value and value == 0:
            return  # zero damage changes nothing; nothing to announce a target for.
        game.create_reflexive_trigger(
            text=with_mana_value(value) + ".",
            controller=player.username,
            source_id=source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


@SPELL_TEXT.rung("s12")
def _parse_loot_then_reflexive_discard_spell(text: str) -> Effect | None:
    """`_LOOT_THEN_REFLEXIVE_DISCARD_RE` on a spell - Flamethrower Sonata."""
    return _loot_then_reflexive_discard_effect(text, for_spell=True)  # type: ignore[return-value]


@ABILITY_TEXT.rung("s20")
def _parse_loot_then_reflexive_discard_ability(text: str) -> AbilityEffect | None:
    """`_LOOT_THEN_REFLEXIVE_DISCARD_RE` on an ability - Narset's -2."""
    return _loot_then_reflexive_discard_effect(text, for_spell=False)  # type: ignore[return-value]


# --------------------------------------------------------------------------
# NW-02 T1: "Each player shuffles the cards from their hand into their library,
# then draws that many cards." (the wheel), optionally followed by more text
# --------------------------------------------------------------------------

_EACH_PLAYER_SHUFFLES_HAND_DRAWS_THAT_MANY_RE = re.compile(
    r"^each player shuffles (?:the cards from )?their hand into their library, "
    r"then draws that many cards\.?$",
    re.IGNORECASE,
)


def _each_player_wheel(game: "Game") -> None:
    """CR 608.2c: each player, in APNAP order (CR 101.4), puts the cards of
    their hand into their library, shuffles it (CR 701.24a) and draws exactly
    as many cards (CR 121.2) - "that many" is that player's own count."""
    for player in _players_in_apnap_order(game):
        hand = list(player.hand)
        if hand:
            game.put_cards_into_library(hand)
        game.shuffle_library(player)
        if hand:
            game.draw_cards(player.username, len(hand))


def _wheel_then_rest(
    text: str, run_rest: Callable[[str], object | None]
) -> tuple[object, ...] | None:
    whole = collapsed(_strip_non_effect_preamble(text))
    if "shuffles" not in whole.lower() or "that many cards" not in whole.lower():
        return None
    sentences = _plain_resolution_sentences(whole)
    if (
        not sentences
        or _EACH_PLAYER_SHUFFLES_HAND_DRAWS_THAT_MANY_RE.fullmatch(sentences[0]) is None
    ):
        return None
    if len(sentences) == 1:
        return ()
    rest = run_rest(" ".join(sentences[1:]))
    if rest is None or _is_notice_only(rest):
        return None
    return (rest,)


@SPELL_TEXT.rung("s18")
def _parse_each_player_wheel_text(text: str) -> Effect | None:
    """The wheel sentence of a spell, then every following instruction read by
    the ordinary dispatcher (Molten Psyche's metalcraft damage)."""
    parts = _wheel_then_rest(text, _spell_effect_or_notice)
    if parts is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        _each_player_wheel(game)
        for rest in parts:
            rest(game, spell)  # type: ignore[operator]

    return effect


@ABILITY_TEXT.rung("s42")
def _parse_each_player_wheel_ability_text(text: str) -> AbilityEffect | None:
    """`_parse_each_player_wheel_text` on a resolving ability."""
    parts = _wheel_then_rest(text, _ability_effect_or_notice)
    if parts is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        _each_player_wheel(game)
        for rest in parts:
            rest(game, ability)  # type: ignore[operator]

    return effect


#: "that player draws a card. If the player is your opponent and has four or
#: more cards in hand, this enchantment deals 2 damage to that player."
#: (Fevered Visions) - the event player draws (CR 121.1), then CR 608.2c's
#: rider reads the hand as it is now, after the draw: the sentence order is
#: the evaluation order, so a hand of three that draws to four qualifies.
#: "That player" is the one the trigger's own event is about (the player
#: whose end step it is); "your opponent" is relative to the ability's
#: controller. The consequence is any ability sentence naming that player.
_THAT_PLAYER_DRAWS_THEN_HAND_SIZE_RE = re.compile(
    r"^that player draws (?P<draw>[^.]+?)\.\s*"
    rf"if the player (?:(?P<opponent>is your opponent) and )?has (?P<n>{COUNT}) or "
    r"(?P<comparison>more|fewer) cards in (?:their )?hand,\s*(?P<rest>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s16")
def _parse_that_player_draws_then_hand_size_clause(text: str) -> AbilityEffect | None:
    """`_THAT_PLAYER_DRAWS_THEN_HAND_SIZE_RE`'s shape; see the banner above."""
    whole = collapsed(_strip_non_effect_preamble(text))
    if not whole.lower().startswith("that player draws "):
        return None
    match = _THAT_PLAYER_DRAWS_THEN_HAND_SIZE_RE.fullmatch(whole)
    if match is None:
        return None
    threshold = parse_count(match.group("n"))
    draw = parse_mixed_effect(f"that player draws {match.group('draw')}.")
    consequence = _ability_effect_or_notice(match.group("rest").strip() + ".")
    if threshold is None or draw is None or consequence is None or _is_notice_only(consequence):
        return None
    wants_more = match.group("comparison").lower() == "more"
    opponent_only = match.group("opponent") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.player is None:
            return
        draw(game, ability)
        if opponent_only and event.player == ability.controller:
            return
        hand = len(game.player(event.player).hand)
        if (hand >= threshold) if wants_more else (hand <= threshold):
            consequence(game, ability)

    return effect


from ._common import (  # noqa: E402
    _DISCARD_A_CARD_RE,
    _DRAW_CARDS_EQUAL_TO_RE,
    _HAND_EXILE_COLOR_WORDS,
    _PLAY_PERMISSION_RE,
    _PLURAL_PERMISSION_SUBJECTS,
    ConditionalClauseNotice,
    PermissionDuration,
    _effect_condition_is_readable,
    _nonland_or_typed_card_matcher,
    _opponents,
    _parse_card_group_qualifier,
    _permanent_id_and_name,
    _permission_duration,
    _players_in_apnap_order,
    _quality_matcher,
    _targets_understood,
    computed_permanents,
)
from .amounts import (  # noqa: E402
    _that_many_or_notice,  # noqa: E402
    count_expression,
    player_counter_count,
)
from .continuous import _who_cant_discard_consequence  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    _spell_effect_or_notice,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .modal import (  # noqa: E402
    _choose_land_from_hand,
    _choose_lands_from_hand,
    _choose_permanents_to_sacrifice,
    _condition_holds_for_stack_object,
    reflexive_consequence_effect,
)
from .removal import (  # noqa: E402
    _cost_sacrificed_stat_total,
    _sacrifice_is_payable,
    _sacrifice_restriction,
)
from .search import _search_quality_is_readable  # noqa: E402
from .text import _plain_resolution_sentences, _strip_non_effect_preamble  # noqa: E402
from .tokens import _is_notice_only, _parse_generic_token_descriptor  # noqa: E402

#: "That creature's controller draws a card." (Nessian Boar) - CR 603.2: the
#: controller of the creature the trigger's event concerns (the blocker, for
#: "becomes blocked by a creature").
_EVENT_REFERENT_CONTROLLER_DRAWS_RE = re.compile(
    rf"^that (?:creature|permanent)'?s controller draws? (?P<n>{COUNT}) cards?\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_event_referent_controller_draws_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EVENT_REFERENT_CONTROLLER_DRAWS_RE`'s shape (ability-only)."""
    if for_spell or " controller draw" not in clause:
        return None
    match = _EVENT_REFERENT_CONTROLLER_DRAWS_RE.fullmatch(clause.strip())
    count = parse_count(match.group("n")) if match else None
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        username = event_player_username(game, stack_object, "that creature's controller")
        if username is not None:
            game.draw_cards(username, count)

    return effect


#: "Draw a card if your life total is greater than or equal to the last noted
#: life total for this enchantment. Then note your life total." (Sigarda's
#: Splendor) - the note is the number its "As this enchantment enters, note your
#: life total." replacement recorded as the permanent's own `choice`
#: (`machines/replacement/enters_choices._note_life_total`).
_DRAW_IF_LIFE_AT_LEAST_NOTED_RE = re.compile(
    r"^draw a card if your life total is greater than or equal to the last noted life total "
    r"for this (?:enchantment|permanent|artifact|creature)\.\s*then note your life total\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_draw_if_life_at_least_noted_then_note_clause(text: str) -> AbilityEffect | None:
    """`_DRAW_IF_LIFE_AT_LEAST_NOTED_RE`'s shape. A permanent with no noted
    total has nothing to compare against, so it draws nothing; the new total is
    noted either way."""
    if "last noted life total" not in text:
        return None
    if _DRAW_IF_LIFE_AT_LEAST_NOTED_RE.fullmatch(collapsed(text)) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        if source is None:
            return
        life = game.player(ability.controller).life
        noted = source.choice
        if (
            noted is not None
            and noted.kind is ChoiceKind.NUMBER
            and noted.value.lstrip("-").isdigit()
            and life >= int(noted.value)
        ):
            game.draw_cards(ability.controller, 1)
        source.choice = Choice(kind=ChoiceKind.NUMBER, value=str(life))

    return effect


#: "`<instructions that discard>`. [If `<condition>`, ]you may cast the discarded card
#: [without paying its mana cost]." (Malcolm, Alluring Scoundrel) - the last sentence
#: names the card an earlier instruction of the same spell or ability discarded.
_CAST_DISCARDED_TAIL_RE = re.compile(
    r"(?:^|(?<=\.)\s+)(?P<tail>(?:if (?P<condition>[^.]+?), )?you may cast "
    r"(?:the discarded card|that card)(?P<free> without paying its mana cost)?\.?)$",
    re.IGNORECASE,
)
_DISCARD_WORD_RE = re.compile(r"\bdiscards?\b", re.IGNORECASE)


def _discard_then_may_cast_discarded(text: str, *, for_spell: bool) -> Callable | None:
    """A paragraph whose last sentence offers a cast of the card it just discarded.

    CR 608.2c: the sentence after the discard refers to what the discard did, so
    the paragraph is read as the instructions that discard, then the optional
    cast (CR 608.2g: cast during resolution, no priority, CR 118.9 for the free
    one, which CR 118.9b lets the player decline). A cast of "that card" is only
    read after a discard, where it can mean nothing else. The condition is
    checked after the earlier instructions ran (CR 608.2c orders them), against
    the source's last known information if it left (CR 608.2h). A discarded land
    is never offered: it can only be played (CR 305.9)."""
    whole = collapsed(_strip_non_effect_preamble(text).strip())
    match = _CAST_DISCARDED_TAIL_RE.search(whole)
    if match is None:
        return None
    head = whole[: match.start()].strip()
    condition = match.group("condition")
    if _DISCARD_WORD_RE.search(head) is None:
        return None
    if condition is not None and not _effect_condition_is_readable(condition):
        return None
    head_effect = (_spell_effect_or_notice if for_spell else _ability_effect_or_notice)(head)
    if head_effect is None or _is_notice_only(head_effect):
        return None
    free = match.group("free") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        before = public_card_ids(game)
        head_effect(game, stack_object)
        discarded = newly_discarded(game, before)
        if not discarded:
            return
        if for_spell:
            source = stack_object
            source_name = stack_object.name
        else:
            source = stack_object.source_or_last_known(game)
            source_name = stack_object.source_name
        if condition is not None and not _condition_holds_for_stack_object(
            game, stack_object, condition, source
        ):
            return
        for card in discarded:
            if card.card.is_land:
                continue
            game.may_cast_during_resolution(
                card,
                controller,
                prompt=f"cast {card.name}" + (" without paying its mana cost" if free else ""),
                source=source_name,
                source_id=source_id_of(stack_object),
                source_name=source_name,
                rule="CR 608.2g",
                pays_mana_cost=not free,
            )

    return effect


@ABILITY_TEXT.rung("s23")
def _parse_discard_then_cast_discarded_ability_text(text: str) -> AbilityEffect | None:
    """The ability side of `_discard_then_may_cast_discarded`."""
    return _discard_then_may_cast_discarded(text, for_spell=False)


@SPELL_TEXT.rung("s21")
def _parse_discard_then_cast_discarded_spell_text(text: str) -> Effect | None:
    """The spell side of `_discard_then_may_cast_discarded`."""
    return _discard_then_may_cast_discarded(text, for_spell=True)
