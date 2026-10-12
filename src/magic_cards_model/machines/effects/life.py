import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from magic_cards_model.phrases import with_indefinite_article

from ...models.card import Color
from ...models.card_state import (
    CardState,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    parse_count,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..ep01_r3_amounts import event_player_username, event_terms
from ..targeting import (
    permanent_description,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from ._common import AbilityEffect, ClauseEffect, Effect, TargetedClause


def gain_life(amount: int) -> Effect:
    """The spell's controller gains `amount` life (CR 118.3)."""

    def effect(game: "Game", spell: CardState) -> None:
        game.controller_of(spell).gain_life(amount)

    return effect


#: "Each opponent loses life equal to the number of creature cards in your
#: graveyard." (Grist, the Hunger Tide's -5) - CR 119.3's life loss, dealt to
#: CR 102.2's "each opponent" rather than a target, with the amount read
#: through the shared `count_expression` (P6) below rather than a one-off
#: reader of its own.
_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE = re.compile(
    r"^each opponent loses life equal to (?P<expr>.+?)\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s35")
def _parse_each_opponent_loses_life_equal_to(text: str) -> AbilityEffect | None:
    """Grist, the Hunger Tide's -5, see `_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE`.

    `None` if `count_expression` cannot read the "equal to" phrase - there is
    no fail-closed notice for this one shape specifically, matching this
    file's existing convention that only a few clause shapes (conditional
    sacrifice, mana adding, the reflexive/anaphoric/delayed/imprint families)
    have a dedicated notice; everything else still silently returns `None`
    from `_ability_effect_or_notice`, unchanged from before this wave.
    """
    match = _EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE.fullmatch(text.strip())
    if match is None:
        return None
    counter = count_expression(match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        amount = counter(game, controller)
        if amount <= 0:
            return
        for opponent in _opponents(game, controller):
            game.lose_life(opponent, amount)

    return effect


#: "Whenever a creature deals combat damage to one of your opponents, its
#: controller may pay 1 life. If they do, they draw a card." (Gix, Yawgmoth
#: Praetor) - CR 118.12's reflexive "may [cost]. If they do, [consequence]",
#: read against the event's own subject's controller (`ability.event.
#: subject_controller`) rather than the ability's own controller ("you") the
#: way every other reflexive "may" clause in this file does. CR 120.1 makes
#: the damaging creature the event's subject, so "its controller" is exactly
#: that creature's controller - not necessarily the player who controls Gix,
#: since the trigger's own condition (CR 603.2, read by `machines/triggers.
#: condition_matches`) names "a creature", not "a creature you control".
#:
#: `_parse_exile_that_players_library_clause` right above is the same "read
#: `ability.event`, not a target" move for "that player" (Ragavan's own
#: anaphora); this is its "may ... if they do" cousin, generalised over the
#: life paid and the cards drawn rather than pinned to Gix's own "1"/"a card"
#: - a future printing of the same shape with a different count reads the
#: same way. No other real printing shares this exact sentence (Tidal Flats
#: and Winter's Chill are close but pay mana, not life, and read a "does not
#: pay" branch this shape has none of), so this is proven on Gix alone.
_ITS_CONTROLLER_MAY_PAY_LIFE_THEN_DRAW_RE = re.compile(
    rf"^its controller may pay (?P<life>{COUNT}) life\.\s*"
    rf"if (?:they do|it does), (?:they|it) draws? (?:(?P<cards>{COUNT}) cards|a card)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_its_controller_may_pay_life_then_draw_clause(text: str) -> AbilityEffect | None:
    """`_ITS_CONTROLLER_MAY_PAY_LIFE_THEN_DRAW_RE`'s shape - Gix, Yawgmoth
    Praetor's whole trigger. Ability-only: nothing in the pool prints this on
    a spell, and a spell has no `ability.event` for "its controller" to read.
    """
    match = _ITS_CONTROLLER_MAY_PAY_LIFE_THEN_DRAW_RE.fullmatch(text.strip())
    if match is None:
        return None
    life = parse_count(match.group("life"))
    cards = 1 if match.group("cards") is None else parse_count(match.group("cards"))
    if life is None or cards is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        username = event.subject_controller if event is not None else None
        if username is None:
            return
        player = game.player(username)
        paid = game.may_pay_life(
            player, life, source=ability.source_name, source_id=source_id_of(ability)
        )
        if paid:
            game.draw_cards(player.username, cards)

    return effect


#: "You may pay any amount of life. If you do, draw that many cards." -
#: Necrodominance's own end-step trigger (CR 119.4, CR 118.12's "if you do").
#: `_PAY_ANY_AMOUNT_OF_LIFE_RE` above reads the identical cost as one
#: player-clause among many for a card that mixes it with other
#: instructions; this is the dedicated whole-sentence pair Necrodominance's
#: own trigger needs, its cost and its "that many" consequence read
#: together the same way `_parse_its_controller_may_pay_life_then_draw_
#: clause` just above pairs Gix's own fixed-amount cost with its own
#: consequence.
_PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE = re.compile(
    r"^you may pay any amount of life\. if you do, draw that many cards\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s35")
def _parse_pay_any_life_then_draw_that_many_clause(text: str) -> AbilityEffect | None:
    """`_PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE`'s shape - Necrodominance's
    whole end-step trigger, via `Game.pay_any_amount_of_life`
    (`DecisionKind.PAY_LIFE_AMOUNT`)."""
    if _PAY_ANY_LIFE_THEN_DRAW_THAT_MANY_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        paid = game.pay_any_amount_of_life(
            player, source=ability.source_name, source_id=source_id_of(ability)
        )
        if paid > 0:
            game.draw_cards(player.username, paid)

    return effect


#: CR 119.5: "If an effect sets a player's life total to a specific number,
#: the player gains or loses the necessary amount of life to end up with the
#: new total." "Your life total becomes `<amount>`" - Elderscale Wurm's own
#: ETB ("if your life total is less than 7, your life total becomes 7", the
#: intervening-if already stripped by `machines/abilities.py` before this
#: ever runs), Form of the Dinosaur's/Form of the Dragon's/Angel of Grace's
#: graveyard activation's/Sway of the Stars's plain numbers, Long Rest's/
#: Oketra's Last Mercy's "equal to your starting life total", The Endstone's
#: "half your starting life total, rounded up" - and Resolute Archangel's own
#: "if your life total is less than your starting life total, it becomes
#: equal to your starting life total", where "it" is CR 607.1 anaphora onto
#: the "your life total" the intervening-if just named, never a different
#: printed shape this reader has seen. `<amount>` is `_life_total_becomes_
#: amount_reader`'s: a number, "equal to `<expr>`", "half `<expr>`, rounded
#: up/down" (through `_amount_term`'s own "your/their starting life total"
#: term), "the number of `<expr>`", "that number", or "the highest/lowest
#: life total among all players". The one "life total becomes" reader for
#: the controller's own life total: `parse_clause_effect` dispatches to it,
#: and `machines/replacement.py`'s "if you would lose the game, instead ..."
#: compilers (Exquisite Archangel's "your life total becomes equal to your
#: starting life total") call it directly; the other subjects ("target
#: player's", "each player's", "that player's") share its amount reader and
#: `Game.set_life_total`, which is where CR 119.5's gain-or-loss is worked
#: out.
_YOUR_LIFE_TOTAL_BECOMES_RE = re.compile(
    r"^(?:(?:have )?your life total becomes?|it becomes) (?P<amount>.+)$", re.IGNORECASE
)


def _life_total_becomes_amount_reader(expr: str) -> "AmountReader | None":
    """The `<amount>` half of "`<subject>`'s life total becomes `<amount>`"
    (CR 119.5), or `None` when it cannot be read. "equal to `<X>`" is just
    `<X>` itself; every other shape is `amount_expression`'s own (a number,
    "half `<X>`, rounded up/down", "the number of `<expr>`", "that number",
    "the highest/lowest life total among all players" - the last four
    through `_amount_term`'s own new branches, above)."""
    text = expr.strip().rstrip(".").strip()
    text = re.sub(r"^equal to\s+", "", text, flags=re.IGNORECASE).strip()
    return amount_expression(text)


def life_total_becomes_effect_for(clause: str) -> ClauseEffect | None:
    """`_YOUR_LIFE_TOTAL_BECOMES_RE`'s shape, or `None`."""
    match = _YOUR_LIFE_TOTAL_BECOMES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    reader = _life_total_becomes_amount_reader(match.group("amount"))
    if reader is None:
        return None

    def life_total_becomes(
        game: "Game", player: Player, source: str, source_id: str | None
    ) -> None:
        new_total = reader(game, player.username, None, 0)
        game.set_life_total(player, new_total)

    return life_total_becomes


#: CR 701.10d: "To double a player's life total, the player gains or loses an
#: amount of life such that their new life total is twice its current
#: value." Angelic Enforcer's (Enduring Angel's back face) own attack
#: trigger: "Whenever this creature attacks, double your life total."
_DOUBLE_YOUR_LIFE_TOTAL_RE = re.compile(r"^double your life total\.?$", re.IGNORECASE)


def _parse_double_your_life_total_clause(clause: str) -> ClauseEffect | None:
    """`_DOUBLE_YOUR_LIFE_TOTAL_RE`'s shape, or `None`."""
    if _DOUBLE_YOUR_LIFE_TOTAL_RE.fullmatch(clause.strip()) is None:
        return None

    def double_life_total(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        game.set_life_total(player, 2 * player.life)

    return double_life_total


#: "Each opponent loses N life unless that player sacrifices a `<quality>`
#: [of their choice] or discards a card." (Perforating Artist, Nicol Bolas
#: the Deceiver's own +3, Torment of Hailfire's repeated process) - CR
#: 118.12's punisher shape widened from `_LOSES_LIFE_UNLESS_RE`'s single
#: fixed action to a *choice* of two, the same two-way optional cost
#: `_MAY_DISCARD_OR_SACRIFICE_IF_YOU_DO_RE` already reads for a plain "you
#: may ... or ...", read here as "each opponent" rather than "you". Both
#: printed orders (sacrifice-then-discard, discard-then-sacrifice) are read,
#: for the identical reason that reader takes both.
_EACH_OPPONENT_LOSES_LIFE_UNLESS_SACRIFICE_OR_DISCARD_RE = re.compile(
    r"^each opponent loses (?P<n>\d+) life unless that player "
    r"(?:sacrifices (?P<restriction_last>[^.]+?) or discards a card"
    r"|discards a card or sacrifices (?P<restriction_first>[^.]+?))\.?$",
    re.IGNORECASE,
)
_OF_THEIR_CHOICE_TAIL_RE = re.compile(r"\s+of their choice$", re.IGNORECASE)


def _parse_each_opponent_loses_life_unless_sacrifice_or_discard_clause(
    clause: str,
) -> ClauseEffect | None:
    """`_EACH_OPPONENT_LOSES_LIFE_UNLESS_SACRIFICE_OR_DISCARD_RE`'s shape.

    Each opponent, independently (CR 102.2), is offered the choice CR
    608.2d already gives a "you may ... or ..." cost - `_sacrifice_
    restriction`/`_sacrifice_is_payable`/`_choose_permanents_to_sacrifice`
    are the exact functions `_parse_may_discard_or_sacrifice_if_you_do_
    clause` uses for its own "you may" version of the same two actions,
    reused rather than re-implemented; only who is being asked, and what
    happens when they decline (losing life, not "nothing"), differ. An
    opponent who can pay neither half loses the life with no question asked
    - CR 608.2d never offers an impossible choice - and one who can pay only
    one half is not asked which, the same "no real choice, no question"
    shape `_parse_may_discard_or_sacrifice_if_you_do_clause` already keeps.
    """
    match = _EACH_OPPONENT_LOSES_LIFE_UNLESS_SACRIFICE_OR_DISCARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = int(match.group("n"))
    restriction_text = (match.group("restriction_last") or match.group("restriction_first")).strip()
    restriction_text = _OF_THEIR_CHOICE_TAIL_RE.sub("", restriction_text).strip()
    restriction = _sacrifice_restriction(restriction_text)
    if restriction is None:
        return None
    sacrifice_option = f"sacrifice {restriction_text}"
    discard_option = "discard a card"

    def effect(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        for opponent in _opponents(game, player.username):
            candidates = restriction.candidates(game, opponent, None)
            payable = {
                sacrifice_option: _sacrifice_is_payable(restriction.quantity, candidates),
                discard_option: len(opponent.hand) >= 1,
            }
            options = tuple(
                option for option in (sacrifice_option, discard_option) if payable[option]
            )
            take_action = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=opponent.username,
                    prompt=(
                        f"{' or '.join(options) if options else sacrifice_option} "
                        f"rather than lose {amount} life"
                    ),
                    source=source,
                    affirmative_is_legal=bool(options),
                    source_id=source_id,
                )
            )
            if not take_action:
                game.lose_life(opponent, amount)
                continue
            chosen = options[0]
            if len(options) > 1:
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=opponent.username,
                        prompt="choose which to do",
                        source=source,
                        options=options,
                        source_id=source_id,
                    )
                )
                assert isinstance(answer, str)
                chosen = answer
            if chosen == discard_option:
                discarded = _discard_cards(game, opponent, 1, source, source_id=source_id)
                if not discarded:
                    game.lose_life(opponent, amount)
            else:
                sacrificed = _choose_permanents_to_sacrifice(
                    game,
                    opponent,
                    restriction,
                    candidates,
                    source_name=source,
                    source_id=source_id,
                )
                if not sacrificed:
                    game.lose_life(opponent, amount)
                else:
                    for permanent in sacrificed:
                        game.sacrifice(permanent)

    return effect


#: "you and that player each gain that much life" - Angel of Destiny's own
#: "Whenever a creature you control deals combat damage to a player, you and
#: that player each gain that much life." The same `TriggerEvent.DEALS_
#: DAMAGE` shape `_EVENT_PLAYER_GETS_THAT_MANY_POISON_RE` above already reads
#: ("that player" is `GameEvent.player`, CR 120.2a's damaged player; "that
#: much" is `GameEvent.amount`, read through `_that_many_or_notice`), with
#: "you" - the resolving ability's own controller (CR 109.5) - gaining
#: alongside rather than instead.
_YOU_AND_EVENT_PLAYER_GAIN_THAT_MUCH_LIFE_RE = re.compile(
    r"^you and that player each gain that much life\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s39", for_spell=False)
def _parse_you_and_event_player_gain_that_much_life_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_YOU_AND_EVENT_PLAYER_GAIN_THAT_MUCH_LIFE_RE`'s shape. Ability-only:
    "that player" and "that much" both point at a triggering event a spell
    never has."""
    if for_spell or _YOU_AND_EVENT_PLAYER_GAIN_THAT_MUCH_LIFE_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack) or stack_object.event is None:
            return
        other = stack_object.event.player
        amount = _that_many_or_notice(
            game,
            clause,
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
            stack_object=stack_object,
        )
        if amount is None or amount <= 0:
            return
        game.gain_life(stack_object.controller, amount)
        if other is not None:
            game.gain_life(other, amount)

    return effect


#: ecl-T8: Mornsong Aria's own draw-step trigger, "At the beginning of each
#: player's draw step, that player loses 3 life, searches their library for
#: a card, puts it into their hand, then shuffles." - the trigger condition
#: itself (`_step_matches`'s own "each `<step>`" fallback, CR 500.6) already
#: reads "each player's draw step" generally; this is the effect that runs
#: once it does, "that player" reading CR 607.1's anaphora onto the
#: triggering event's own subject (`event.player`, the player whose step
#: just began) the identical way `_THAT_PLAYER_MILLS_THAT_MANY_RE` above
#: reads it for a lost-life event instead of a step. Maralen of the
#: Mornsong's real printing (verified with `resolve_cards`) is the same
#: sentence, worded identically.
_THAT_PLAYER_LOSES_LIFE_SEARCHES_PUTS_IN_HAND_RE = re.compile(
    rf"^that player loses (?P<n>{COUNT}) life, searches (?:their|its) library for a card, "
    r"puts it into (?:their|its) hand, then shuffles\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s33", for_spell=False)
def _parse_that_player_loses_life_searches_puts_in_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYER_LOSES_LIFE_SEARCHES_PUTS_IN_HAND_RE`'s shape, or `None`.

    No quality restriction at all ("a card") - `_search_library` with an
    always-true predicate, the same "any card" reading Card Draw's own bare
    "search your library for a card" already gets. CR 608.2c's own order:
    the life loss happens first, then the search, whether or not the loss
    actually reduced the player's life (CR 119.4 clamps at zero, never
    refuses the instruction).
    """
    if for_spell:
        return None
    match = _THAT_PLAYER_LOSES_LIFE_SEARCHES_PUTS_IN_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        username = stack_object.event.player
        if username is None:
            return
        player = game.player(username)
        source_name = stack_object.source_name
        source_id = source_id_of(stack_object)
        if amount > 0:
            game.lose_life(player, amount)
        found = _search_library(
            game, player, lambda _state: True, source=source_name, source_id=source_id
        )
        if found is not None:
            player.add(found, Zone.HAND)

    return effect


#: Living Destiny: "You gain life equal to the revealed card's mana value." The
#: card that paid this spell's additional cost (CR 118.8a), read back off
#: `Game.cast_record(spell).additional_cost_cards` the way Fling's "the
#: sacrificed creature's power" and Swallow Whole's "the creature tapped to pay
#: this spell's additional cost" already are. The verb says which cost paid it;
#: the characteristic is CR 202.3's mana value or CR 208.1's power or toughness,
#: read off the card wherever paying it left it.
_GAIN_LIFE_EQUAL_TO_ADDITIONAL_COST_CARD_RE = re.compile(
    r"^you gain life equal to the (?:revealed|sacrificed|exiled|discarded|tapped) "
    r"(?:card|creature|permanent|artifact)'?s (?P<attr>mana value|power|toughness)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s25", for_spell=FORWARD)
def _parse_gain_life_equal_to_additional_cost_card_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_GAIN_LIFE_EQUAL_TO_ADDITIONAL_COST_CARD_RE`'s shape, or `None`.

    Spell-only: an additional cost is a spell's (CR 118.8a), and only a spell
    has a `Game.cast_record` to read it back from. Gains nothing when no card
    was recorded or the characteristic cannot be read (a `*` power off the
    battlefield), and never a negative amount (CR 107.1b).
    """
    if not for_spell:
        return None
    match = _GAIN_LIFE_EQUAL_TO_ADDITIONAL_COST_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    attribute = match.group("attr").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        record = game.cast_record(stack_object)
        if not record.additional_cost_cards:
            return
        card_state = game.find_by_id(record.additional_cost_cards[0])
        if not isinstance(card_state, CardState):
            return
        if attribute == "mana value":
            value: float | int | None = card_state.mana_value
        elif attribute == "power":
            value = card_state.power
        else:
            value = card_state.toughness
        if value is None:
            return
        game.gain_life(game.controller_of(stack_object), max(int(value), 0))

    return effect


def _loses_life_unless_step(match: re.Match[str]) -> ClauseEffect | None:
    """`_LOSES_LIFE_UNLESS_RE`'s step, for one player: they choose whether to
    take the action instead (CR 608.2d - offered only when they can, since
    CR 608.2d offers no impossible choice), and lose the life if they do not
    (CR 119.3)."""
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    description = match.group("description")
    discards = description is None
    requirement = None
    if not discards:
        requirement = permanent_description(description.strip())
        if requirement is None:
            return None
        sacrifice = _sacrifice_of_choice_clause_effect(
            description.strip(), 1, with_indefinite_article(description.strip())
        )

    def step(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        if discards:
            able = bool(player.hand)
            prompt = f"discard a card rather than lose {amount} life"
        else:
            able = any(
                requirement.rejects(permanent, player.username, game) is None  # type: ignore[union-attr]
                for permanent in game.permanents_controlled_by(player.username)
            )
            prompt = f"sacrifice {with_indefinite_article(description.strip())} rather than lose {amount} life"  # noqa: E501
        if able and game.may(player, prompt, source=source, source_id=source_id):
            if discards:
                _discard_cards(game, player, 1, source, source_id=source_id)
            else:
                sacrifice(game, player, source, source_id)
            return
        game.lose_life(player, amount)

    return step


#: Dawnglow Infusion: "You gain X life if {G} was spent to cast this spell
#: and X life if {W} was spent to cast this spell." CR 707.2's own worked
#: example of what a copy does *not* carry: "Because mana isn't an object, a
#: copy of Dawnglow Infusion won't cause you to gain any life, no matter what
#: mana was spent to cast the original spell" - `Game.copy_spell` already
#: excludes `mana_spent` from what it writes onto a copy's own `CastRecord`
#: (see that method's own docstring), so a copy's resolution reads an empty
#: `mana_spent` and gains nothing here with no special case for `is_copy`.
#: Two independent conditions in one instruction, not CR 608.2c's sequential
#: clauses ("Do both if {G}{W} was spent" - reminder text, CR 207.2) - read
#: whole rather than split at "and", the same reason `_CONVERGE_EXILE_RE`
#: above and `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` are whole-text matches.
#: Generalised over which two colors are named (`_COLOR_LETTERS`) rather than
#: hardcoded to {G}/{W}, so a future card sharing this exact template with a
#: different color pair is covered for free; Dawnglow Infusion is the only
#: printing in the pool today. Matched on the *literal* "X" - like
#: `_parse_x_life_mass_debuff` above, this needs `Game.cast_record(spell).
#: x_value` itself (CR 107.3a) multiplied by however many of the two named
#: colors were actually spent (CR 601.2h), which `effect_for`'s own
#: substitution cannot express (it would collapse "X life ... and X life"
#: into two copies of one fixed number, not "count how many conditions
#: held").
_GAIN_LIFE_IF_COLOR_SPENT_RE = re.compile(
    r"^you gain x life if (?P<color1>\{[wubrg]\}) was spent to cast this spell "
    r"and x life if (?P<color2>\{[wubrg]\}) was spent to cast (?:this spell|it)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_gain_life_if_color_spent_clause(effect_text: str) -> Effect | None:
    """`_GAIN_LIFE_IF_COLOR_SPENT_RE`'s shape, or `None` if this is not it."""
    match = _GAIN_LIFE_IF_COLOR_SPENT_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    color1 = Color(match.group("color1").strip("{}").upper())
    color2 = Color(match.group("color2").strip("{}").upper())

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record(spell)
        x_value = record.x_value
        if x_value <= 0:
            return
        total = 0
        if record.mana_of_color_spent(color1) > 0:
            total += x_value
        if color2 != color1 and record.mana_of_color_spent(color2) > 0:
            total += x_value
        if total > 0:
            game.gain_life(game.controller_of(spell), total)

    return effect


#: A leading "You can't lose the game this turn and your opponents can't win
#: the game this turn." sentence (Angel's Grace), then whatever else the
#: spell says - Angel's Grace's "Until end of turn, damage that would reduce
#: your life total to less than 1 reduces it to 1 instead.", the created
#: replacement `_parse_created_replacement_spell_text` reads (CR 614.1a).
_GAME_OUTCOME_PROHIBITION_SENTENCE_RE = re.compile(
    r"^(?P<first>you can't (?:lose|win) the game[^.\n]*\.|"
    r"your opponents can't (?:lose|win) the game[^.\n]*\.)\s*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_lose_the_game_prohibition_then_rest(effect_text: str) -> Effect | None:
    """A spell whose first sentence is a turn-long "can't lose the game" /
    "your opponents can't win the game" (`turn_scoped_riders.
    game_outcome_prohibition_rider`, CR 101.2, CR 611.2a) and whose rest, if
    any, the ordinary spell dispatcher reads. CR 608.2c: in the order
    written. Either half unread leaves the whole unread (fail closed)."""
    if "the game" not in effect_text:
        return None
    match = _GAME_OUTCOME_PROHIBITION_SENTENCE_RE.match(effect_text.strip())
    if match is None:
        return None
    prohibition = game_outcome_prohibition_rider(match.group("first"))
    if prohibition is None:
        return None
    rest_text = match.group("rest").strip()
    rest = _spell_effect_or_notice(rest_text) if rest_text else None
    if rest_text and (rest is None or _is_notice_only(rest)):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        prohibition(game, spell)
        if rest is not None:
            game.announce_batched_events()  # CR 603.2c: one event per instruction
            rest(game, spell)

    return effect


#: "you lose the game." as a triggered ability's whole instruction - Lich's
#: Mastery's "When Lich's Mastery leaves the battlefield, you lose the game."
#: (CR 603.6c). CR 104.3e's stated loss, so `Game.player_loses_the_game` both
#: honours a "can't lose the game" still in force (CR 101.2) and offers it to
#: "if you would lose the game, instead" replacements (CR 614).
_YOU_LOSE_THE_GAME_RE = re.compile(r"^you lose the game\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s9")
def _parse_you_lose_the_game_clause(text: str) -> AbilityEffect | None:
    """`_YOU_LOSE_THE_GAME_RE`'s shape: the ability's controller loses."""
    if "lose the game" not in text or _YOU_LOSE_THE_GAME_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.player_loses_the_game(ability.controller)

    return effect


#: "`<instruction>`. Then if `<condition>`, `<you lose|enchanted player
#: loses>` the game." - Marina Vendrell's Grimoire ("Discard that many cards.
#: Then if you have no cards in hand, you lose the game.") and Sinner's
#: Judgment ("Put a judgment counter on this Aura. Then if there are three or
#: more judgment counters on it, enchanted player loses the game."). The
#: instruction is followed first (CR 608.2c) and the condition read after it;
#: the loss is CR 104.3e's, through `Game.player_loses_the_game`.
_THEN_IF_LOSES_THE_GAME_RE = re.compile(
    r"^(?P<head>.+?)\. then if (?:(?P<empty_hand>you have no cards in hand)|there are "
    r"(?P<n>\w+) or more (?P<kind>[\w+/-]+) counters on it), "
    r"(?P<who>you lose|enchanted player loses) the game\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_then_if_loses_the_game_clause(text: str) -> AbilityEffect | None:
    """`_THEN_IF_LOSES_THE_GAME_RE`'s shape, or `None`."""
    if "the game" not in text:
        return None
    match = _THEN_IF_LOSES_THE_GAME_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    head = _ability_effect_or_notice(match.group("head").strip() + ".")
    if head is None or _is_notice_only(head):
        return None
    threshold: int | None = None
    if match.group("n") is not None:
        threshold = parse_count(match.group("n"))
        if threshold is None:
            return None
    kind = match.group("kind")
    enchanted = match.group("who").lower().startswith("enchanted")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        head(game, ability)
        source = ability.source(game)
        if threshold is not None:
            if source is None or source.counters[kind] < threshold:
                return
        elif game.player(ability.controller).hand:
            return
        if not enchanted:
            game.player_loses_the_game(ability.controller)
            return
        attachment = source.attachment if source is not None else None
        if (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and attachment is not None
            and attachment.username is not None
        ):
            game.player_loses_the_game(attachment.username)

    return effect


#: "for each 1 life you lost, exile a permanent you control or a card from
#: your hand or graveyard." - Lich's Mastery's "Whenever you lose life, ..."
#: (CR 119.3). The count is the triggering life-loss event's own amount
#: (`amounts.that_many`, CR 603.2c); the objects are the controller's choice
#: as the ability resolves (CR 608.2d), any mix of the places the clause
#: lists, and each is exiled (CR 701.13a). Fewer objects than the count
#: exiles every one of them. The places read: "a permanent you control",
#: "a card from your hand", "a card from your graveyard", and "a card from
#: your hand or graveyard", joined by "or".
_EXILE_PLACE = (
    r"a permanent you control|a card from your (?:hand|graveyard)(?: or (?:hand|graveyard))?"
)
_EXILE_FOR_EACH_LIFE_LOST_RE = re.compile(
    rf"^for each 1 life you lost, exile "
    rf"(?P<places>(?:{_EXILE_PLACE})(?: or (?:{_EXILE_PLACE}))*)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_exile_for_each_life_lost_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_FOR_EACH_LIFE_LOST_RE`'s shape - see the banner above."""
    if "life you lost" not in text:
        return None
    match = _EXILE_FOR_EACH_LIFE_LOST_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    places = match.group("places").lower()
    from_battlefield = "a permanent you control" in places
    from_hand = "hand" in places
    from_graveyard = "graveyard" in places

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
        candidates: list[CardState] = []
        if from_battlefield:
            candidates.extend(game.permanents_controlled_by(player.username))
        if from_hand:
            candidates.extend(player.hand)
        if from_graveyard:
            candidates.extend(player.graveyard)
        if not candidates:
            return
        amount = min(count, len(candidates))
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {amount} to exile",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=amount,
                exact=True,
                default_cards=tuple(state.id for state in candidates[:amount]),
                cards=tuple(state.id for state in candidates),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in candidates}
        game.exile_cards([by_id[card_id] for card_id in chosen])

    return effect


#: "you may pay `<N>` life. If you do, `<consequence>`." - Voracious
#: Tome-Skimmer's "Whenever you cast a spell during an opponent's turn, you
#: may pay 1 life. If you do, draw a card." and Crossway Troublemakers'
#: "Whenever a Vampire you control dies, you may pay 2 life. If you do, draw
#: a card." - the life twin of `_MAY_PAY_MANA_IF_YOU_DO_RE` (CR 118.12's
#: "if you do", CR 119.4: a player can pay life only if their life total is
#: at least that amount).
_MAY_PAY_LIFE_IF_YOU_DO_RE = re.compile(
    rf"^you may pay (?P<life>{COUNT}) life\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_pay_life_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_PAY_LIFE_IF_YOU_DO_RE`'s shape; the consequence is
    `pay_consequence_effect`'s, shared with the mana and energy twins."""
    match = _MAY_PAY_LIFE_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    life = parse_count(match.group("life"))
    if life is None:
        return None
    consequence = pay_consequence_effect(match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        paid = game.may_pay_life(
            player, life, source=ability.source_name, source_id=source_id_of(ability)
        )
        if paid:
            consequence(game, ability)

    return effect


#: "They gain/lose N life." - Sheoldred, the Apocalypse's own "Whenever an
#: opponent draws a card, they lose 2 life." "They" is CR 607.1's own
#: anaphora back to the player the trigger's condition named ("an opponent"),
#: read off `GameEvent.player` - the same event field `TriggerEvent.
#: DRAWS_A_CARD`/`GAINS_LIFE`'s own condition matcher already reads for "an
#: opponent" (`machines/triggers.py`) - never the resolving ability's
#: controller, which is why this cannot go through `parse_clause_effect`'s
#: ordinary "you gain/lose life" reading (`_GAIN_LIFE_RE`/`_LOSE_LIFE_RE`):
#: that family always means the controller.
_THEY_GAIN_OR_LOSE_LIFE_RE = re.compile(
    rf"^they (?P<verb>gains?|loses?) (?P<n>{COUNT}) life$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_they_gain_or_lose_life_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_THEY_GAIN_OR_LOSE_LIFE_RE`'s shape. Ability-only: a spell has no
    `ability.event` to read "they" against."""
    if for_spell:
        return None
    match = _THEY_GAIN_OR_LOSE_LIFE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    gains = match.group("verb").lower().startswith("gain")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.player is None:
            return
        player = game.player(event.player)
        if gains:
            game.gain_life(player, amount)
        else:
            game.lose_life(player, amount)

    return effect


#: "Its controller loses that much life." (Visions of Brutality), "they lose
#: half their life, rounded up." (Grievous Wound), "that player loses ..." - a
#: life change aimed at the player the trigger's event concerns (CR 603.2):
#: "they" / "that player" is `GameEvent.player`, "its controller" the
#: controller of the event's subject (the damage source). The amount is the
#: event's own (`GameEvent.amount`, "that much", CR 603.2c) or half the
#: player's current life total (CR 107.1a - the card prints the rounding).
_EVENT_PLAYER_LIFE_RE = re.compile(
    r"^(?P<who>they|that player|its controller|that (?:creature|permanent)'?s controller) "
    r"(?P<verb>gains?|loses?) (?:(?P<much>that much life)|half their life,\s*rounded "
    r"(?P<direction>up|down))\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_event_player_life_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_EVENT_PLAYER_LIFE_RE`'s shape. Ability-only: a spell has no event."""
    if for_spell or not clause.startswith(
        (
            "they ",
            "They ",
            "that player",
            "That player",
            "its controller",
            "Its controller",
            "that creature",
            "That creature",
            "that permanent",
            "That permanent",
        )
    ):
        return None
    match = _EVENT_PLAYER_LIFE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    who = match.group("who").lower()
    gains = match.group("verb").lower().startswith("gain")
    half_rounds_up = (match.group("direction") or "").lower() == "up"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        username = event_player_username(game, stack_object, who)
        if username is None:
            return
        player = game.player(username)
        if match.group("much"):
            amount = stack_object.event.amount if stack_object.event is not None else None
        else:
            life = max(player.life, 0)
            amount = (life + 1) // 2 if half_rounds_up else life // 2
        if not amount or amount <= 0:
            return
        if gains:
            game.gain_life(player, amount)
        else:
            game.lose_life(player, amount)

    return effect


#: "[Then] if `<condition>`, target player/opponent loses the game." - Mirrodin
#: Besieged's Phyrexian half ("... Then if there are fifteen or more artifact
#: cards in your graveyard, target opponent loses the game."). CR 104.3e's
#: stated loss on a target chosen as the ability was put on the stack (CR
#: 601.2c via 603.3d); the condition is read by `Game.condition_holds` as the
#: ability resolves, and an unreadable one loses nothing (the same
#: conservative fallback the "you win the game" twin states).
_IF_CONDITION_TARGET_LOSES_THE_GAME_RE = re.compile(
    r"^(?:then )?if (?P<condition>.+?),\s*target (?P<who>player|opponent) loses the game\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_if_condition_target_loses_the_game_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_CONDITION_TARGET_LOSES_THE_GAME_RE`'s shape. Ability-only here: the
    one printing is a triggered ability."""
    if for_spell or "loses the game" not in clause.lower():
        return None
    match = _IF_CONDITION_TARGET_LOSES_THE_GAME_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(
        f"target {match.group('who')}", allow_player_targets=True
    ):
        return None
    condition = match.group("condition").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        controller = game.controller_of(stack_object).username
        if not game.condition_holds(controller, condition, stack_object.source(game)):
            return
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.player_loses_the_game(target.username)

    return effect


#: "Each player loses 1 life for each attacking creature they control." (Batwing
#: Brume) - CR 119.3's life change, one per object of the named group *that
#: player* controls (CR 102.1's "each player", CR 101.4's turn order), so the
#: count is taken per player rather than once for the resolving spell's
#: controller. "They control" is the printed word for what `count_expression`
#: reads as "you control" with the counted player as "you".
_EACH_PLAYER_LIFE_PER_THEY_CONTROL_RE = re.compile(
    rf"^each (?P<who>player|opponent) (?P<verb>gains?|loses?) (?P<n>{COUNT}) life "
    r"for each (?P<group>[^,.]+?) they control$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_each_player_life_per_group_they_control_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_LIFE_PER_THEY_CONTROL_RE`'s shape: every player (or every
    opponent of the controller) gains or loses N life times the size of the
    named group they themselves control."""
    if " for each " not in clause.lower() or " they control" not in clause.lower():
        return None
    match = _EACH_PLAYER_LIFE_PER_THEY_CONTROL_RE.fullmatch(clause.strip())
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    counter = count_expression(f"{match.group('group')} you control")
    if unit is None or counter is None:
        return None
    gains = match.group("verb").lower().startswith("gain")
    opponents_only = match.group("who").lower() == "opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for player in list(game.players_in_game):
            if opponents_only and player.username == controller.username:
                continue
            amount = unit * counter(game, player.username)
            if amount <= 0:
                continue
            if gains:
                game.gain_life(player, amount)
            else:
                game.lose_life(player, amount)

    return effect


#: Master of Cruelties' own attack trigger: "Whenever this creature attacks
#: a player and isn't blocked, that player's life total becomes 1." CR
#: 607.1's "that player" anaphora onto the very player the condition just
#: named - the defending player, `GameEvent.defender_controller` on the
#: `TriggerEvent.ATTACKS_UNBLOCKED` event `Game.declare_blockers` emits
#: (CR 508.3f/509.3g), not `GameEvent.player` (`_parse_that_player_clause`'s
#: own referent, a different field for a different event shape entirely).
#: The possessive "'s" is why this cannot reuse that reader anyway (see
#: `_LIFE_TOTAL_BECOMES_TARGET_RE`'s own docstring for the identical gap on
#: "target player's").
_THAT_PLAYERS_LIFE_TOTAL_BECOMES_RE = re.compile(
    r"^that player'?s life total becomes (?P<amount>.+)$", re.IGNORECASE
)


def _parse_that_players_life_total_becomes_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYERS_LIFE_TOTAL_BECOMES_RE`'s shape. Ability-only, the same
    restriction `_parse_that_player_clause` states: a resolving spell has no
    `ability.event` to resolve "that player" against."""
    if for_spell:
        return None
    match = _THAT_PLAYERS_LIFE_TOTAL_BECOMES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount_reader = _life_total_becomes_amount_reader(match.group("amount"))
    if amount_reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.defender_controller is None:
            return
        player = game.player(event.defender_controller)
        new_total = amount_reader(game, player.username, None, 0)
        game.set_life_total(player, new_total)

    return effect


#: "You gain life equal to the sacrificed creature's toughness." - Ayli,
#: Eternal Pilgrim's own "{1}, Sacrifice another creature:" ability, and
#: Temple of Aclazotz's (Arguel's Blood Fast's transformed back)
#: "{T}, Sacrifice a creature:" ability, word for word. The identical CR
#: 602.2b timing `_DRAW_EQUAL_TO_SACRIFICED_CREATURE_POWER_THEN_DISCARD_RE`
#: above already documents: the creature paid as the activation's own cost is
#: gone (CR 400.7) before this ability is even on the stack, so its power/
#: toughness is `_cost_sacrificed_stat_total`'s last-known snapshot.
#: `attribute` is read generically - power or toughness - rather than pinned
#: to Ayli's own "toughness".
_GAIN_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE = re.compile(
    r"^you gain life equal to the sacrificed creature'?s (?P<attribute>power|toughness)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_gain_life_equal_to_sacrificed_creature_clause(text: str) -> AbilityEffect | None:
    """`_GAIN_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE`'s shape."""
    match = _GAIN_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE.fullmatch(text.strip())
    if match is None:
        return None
    attribute = match.group("attribute").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        total = _cost_sacrificed_stat_total(game, ability, attribute)
        if total > 0:
            game.gain_life(game.controller_of(ability).username, total)

    return effect


#: "Each opponent loses life equal to the sacrificed creature's power." -
#: Jarad, Golgari Lich Lord's "{1}{B}{G}, Sacrifice another creature:"
#: ability: the untargeted twin of the target-player loss below.
_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE = re.compile(
    r"^each opponent loses life equal to the sacrificed creature'?s "
    r"(?P<attribute>power|toughness)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_each_opponent_loses_life_equal_to_sacrificed_creature_clause(
    text: str,
) -> AbilityEffect | None:
    """`_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE`'s shape."""
    match = _EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE.fullmatch(text.strip())
    if match is None:
        return None
    attribute = match.group("attribute").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        total = _cost_sacrificed_stat_total(game, ability, attribute)
        if total <= 0:
            return
        for opponent in _opponents(game, game.controller_of(ability).username):
            game.lose_life(opponent, total)

    return effect


#: "Target opponent loses life equal to the sacrificed creature's toughness."
#: - Catapult Captain's own "{2}{B}, {T}, Sacrifice another creature:"
#: ability: `_GAIN_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE`'s loss twin, with the
#: affected player a target chosen as the ability was put on the stack
#: (CR 601.2c via 602.2b) rather than the controller.
_TARGET_PLAYER_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE = re.compile(
    r"^target (?P<who>player|opponent) loses life equal to the sacrificed "
    r"creature'?s (?P<attribute>power|toughness)\.?$",
    re.IGNORECASE,
)


def _parse_target_player_loses_life_equal_to_sacrificed_creature_clause(
    clause: str,
) -> TargetedClause | None:
    """`_TARGET_PLAYER_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE`'s shape.
    Ability-only: a spell has no activation cost to have sacrificed to."""
    match = _TARGET_PLAYER_LOSES_LIFE_EQUAL_TO_SACRIFICED_CREATURE_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(
        f"target {match.group('who')}", allow_player_targets=True
    ):
        return None
    attribute = match.group("attribute").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        total = _cost_sacrificed_stat_total(game, stack_object, attribute)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player) and total > 0:
                game.lose_life(target, total)

    return effect


#: "you may pay {W/B}. If you do, each opponent loses 1 life and you gain
#: life equal to the total life lost this way." - extort's own effect (CR
#: 702.101a, `machines/keywords._extort_ability`). CR 118.12's optional
#: payment, then each opponent loses N (CR 119.3) and the controller gains
#: exactly what was lost in total (a player who can't lose life loses none,
#: so adds none).
_MAY_PAY_THEN_DRAIN_TOTAL_RE = re.compile(
    rf"^you may pay (?P<mana>(?:\{{[^}}]+\}})+)\.\s*if you do,\s*each opponent loses "
    rf"(?P<n>{COUNT}) life and you gain life equal to the total life lost this way\.?$",
    re.IGNORECASE,
)


def _parse_may_pay_then_drain_total(text: str) -> AbilityEffect | None:
    """`_MAY_PAY_THEN_DRAIN_TOTAL_RE`'s shape, or `None`."""
    match = _MAY_PAY_THEN_DRAIN_TOTAL_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    cost = ManaCost.parse(match.group("mana"))
    amount = parse_count(match.group("n"))
    if not amount:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        if not game.may_pay_mana_cost(
            player, cost, source=ability.source_name, source_id=source_id_of(ability)
        ):
            return
        lost = 0
        for opponent in _opponents(game, player.username):
            before = opponent.life
            game.lose_life(opponent, amount)
            lost += max(before - opponent.life, 0)
        if lost:
            game.gain_life(player, lost)

    return effect


#: "you may pay 2 life. If you do, `<rest>`" (The Kingpin of Crime) - CR
#: 119.4's optional life payment, and the rest only if it was paid (CR
#: 118.12), for a rest one of the readers here reads.
_MAY_PAY_LIFE_THEN_RE = re.compile(
    rf"^you may pay (?P<n>{COUNT}) life\.\s*if you do,\s*(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_may_pay_life_then_rider(text: str) -> AbilityEffect | None:
    """`_MAY_PAY_LIFE_THEN_RE` over `_parse_until_eot_assigns_toughness`."""
    match = _MAY_PAY_LIFE_THEN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    rest = _parse_until_eot_assigns_toughness(match.group("rest"))
    if not amount or rest is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if game.may_pay_life(
            game.controller_of(ability),
            amount,
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            rest(game, ability)

    return effect


#: "Whenever another creature you control dies, you gain life equal to its
#: toughness." - South Wind Avatar's own dies trigger - and Righteous
#: Valkyrie's own "Whenever another Angel or Cleric you control enters, you
#: gain life equal to that creature's toughness." Both are CR 400.7 anaphora
#: back to the very object the trigger condition already matched (CR
#: 603.10a's own look-back, CR 700.4) - "it" when the object left the
#: battlefield and the pronoun is all that is left to call it (South Wind
#: Avatar's own dies trigger), "that creature" when it has not (Righteous
#: Valkyrie's own enters trigger, where the object is still there to be named
#: directly) - read off `AbilityOnStack.event` the same way `event_subject_
#: power` already reads a dying creature's power for Gruff Triplets' own
#: dies trigger. `CardState.toughness` already falls back to `last_known_
#: toughness` (CR 608.2h) the moment the object leaves the battlefield, so
#: nothing further is needed to read either phrasing once resolution asks.
_GAIN_LIFE_EQUAL_TO_EVENT_SUBJECT_TOUGHNESS_RE = re.compile(
    r"^you gain life equal to (?:its|that creature'?s) toughness\.?$", re.IGNORECASE
)


def _parse_gain_life_equal_to_event_subject_toughness_clause(text: str) -> AbilityEffect | None:
    """`_GAIN_LIFE_EQUAL_TO_EVENT_SUBJECT_TOUGHNESS_RE`'s shape.

    Through `Game.gain_life`, not `Player.gain_life`, the same distinction
    `parse_clause_effect`'s own `_GAIN_LIFE_RE` branch already draws: CR 119.9
    treats this as an ordinary life-gain event, which is what lets South Wind
    Avatar's own second ability ("Whenever you gain life, each opponent loses
    1 life.") see it. A toughness of 0 or less, or no event subject at all
    (an ability somehow reaching resolution with nothing to be anaphoric to),
    gains no life rather than a negative or guessed amount.
    """
    if _GAIN_LIFE_EQUAL_TO_EVENT_SUBJECT_TOUGHNESS_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is None:
            return
        toughness = subject.toughness
        if toughness is None or toughness <= 0:
            return
        game.gain_life(game.player(ability.controller), toughness)

    return effect


#: "You gain life equal to the damage dealt this way." - the second clause of a
#: damage spell (Brightflame, Corrupt, Rite of Consumption, Enter the
#: God-Eternals), CR 608.2c's later text pointing back at the earlier clause.
#: "Damage dealt" is what `Game.deal_damage` reports landed (CR 120.3, after
#: prevention): the caller sums it over every recipient the clause damaged and
#: hands the total to the effect this returns. Not a `MIXED_CLAUSE` rung: on its
#: own the sentence has no damage to refer back to, so reading it standing alone
#: would gain nothing and look handled. `machines/damage_backrefs.py` reads the
#: whole sequence and owns the total; this is the one reader of the sentence.
_GAIN_LIFE_EQUAL_TO_DAMAGE_DEALT_RE = re.compile(
    r"^you gain life equal to the damage dealt this way\.?$", re.IGNORECASE
)


def gain_life_equal_to_damage_dealt(sentence: str) -> "Callable[[Game, str, int], None] | None":
    """`(game, controller username, damage dealt) -> None` for the sentence
    above, or None for any other sentence. Gains nothing for zero damage."""
    if _GAIN_LIFE_EQUAL_TO_DAMAGE_DEALT_RE.fullmatch(sentence.strip()) is None:
        return None

    def gain(game: "Game", controller: str, dealt: int) -> None:
        if dealt > 0:
            game.gain_life(controller, dealt)

    return gain


#: "You gain life equal to target creature's power.[ The next time that
#: creature would deal damage this turn, prevent that damage.]" (Soul's
#: Grace; Dazzling Reflection): the power as the spell resolves (CR 608.2h),
#: then CR 615.1's next-instance shield on that creature as a source - the
#: same `ShieldKind.NEXT_INSTANCE` record Awe Strike's "the next time target
#: creature would deal damage this turn" builds, ended by cleanup.
_GAIN_LIFE_EQUAL_TO_TARGET_POWER_RE = re.compile(
    r"^you gain life equal to target creature's power\."
    r"(?P<shield>\s*the next time that creature would deal damage this turn, prevent that "
    r"damage\.)?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_gain_life_equal_to_target_power_text(text: str) -> Effect | None:
    """`_GAIN_LIFE_EQUAL_TO_TARGET_POWER_RE`'s shape. An illegal target means
    the spell does nothing (CR 608.2b: its only target is gone)."""
    if not text.lower().startswith("you gain life equal to target creature's power"):
        return None
    match = _GAIN_LIFE_EQUAL_TO_TARGET_POWER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    shields = match.group("shield") is not None

    def effect(game: "Game", spell: CardState) -> None:
        from ...models.game import PreventionShield, ShieldKind

        creatures = [
            target for target in game.resolve_card_targets(spell) if target.zone is Zone.BATTLEFIELD
        ]
        if not creatures:
            return
        creature = creatures[0]
        controller = game.controller_of(spell).username
        power = max(game.power_of(creature) or 0, 0)
        if power > 0:
            game.gain_life(controller, power)
        if shields:
            game.create_prevention_shield(
                PreventionShield(
                    kind=ShieldKind.NEXT_INSTANCE,
                    label=f"prevent the next damage {creature.name} would deal this turn",
                    controller=controller,
                    source_id=creature.id,
                )
            )

    return effect


from ..turn_scoped_riders import game_outcome_prohibition_rider  # noqa: E402
from ._common import (  # noqa: E402
    AmountReader,
    _opponents,
    _targets_understood,
    pay_consequence_effect,
)
from .amounts import _that_many_or_notice, amount_expression, count_expression  # noqa: E402
from .damage import _parse_until_eot_assigns_toughness  # noqa: E402
from .dispatch import _ability_effect_or_notice, _spell_effect_or_notice  # noqa: E402
from .draw_discard import _discard_cards  # noqa: E402
from .modal import _choose_permanents_to_sacrifice  # noqa: E402
from .removal import (  # noqa: E402
    _cost_sacrificed_stat_total,
    _sacrifice_is_payable,
    _sacrifice_of_choice_clause_effect,
    _sacrifice_restriction,
)
from .search import _search_library  # noqa: E402
from .text import _strip_non_effect_preamble  # noqa: E402
from .tokens import _is_notice_only  # noqa: E402

#: "You lose life equal to its mana value." off a "whenever you cast a spell"
#: trigger (Teval, Arbiter of Virtue) - "its" is the spell the cast event names
#: (CR 603.2, CR 202.3e).
_LOSE_LIFE_EQUAL_TO_CAST_SPELL_MV_RE = re.compile(
    r"^you lose life equal to (?:its|that spell'?s) mana value\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s40", before=["dispatch.parse_mixed_effect"])
def _parse_lose_life_equal_to_cast_spell_mana_value_text(text: str) -> AbilityEffect | None:
    """`_LOSE_LIFE_EQUAL_TO_CAST_SPELL_MV_RE`'s shape."""
    if "mana value" not in text:
        return None
    stripped = " ".join(text.strip().split())
    if _LOSE_LIFE_EQUAL_TO_CAST_SPELL_MV_RE.fullmatch(stripped) is None:
        return None
    from . import parse_mixed_effect

    with event_terms():
        return parse_mixed_effect(stripped)
