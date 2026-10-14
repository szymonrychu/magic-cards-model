"""A player reveals some cards from their hand; you choose one; they discard
or exile it - and an exiled instant or sorcery may be cast for as long as you
control the source (ECL).

"target opponent reveals X cards from their hand, where X is the number of
Goblins you control. You choose one of those cards. That player exiles it.
If an instant or sorcery card is exiled this way, you may cast it for as long
as you control this creature, and mana of any type can be spent to cast that
spell." (Taster of Wares) and "target player reveals X cards from their hand,
where X is the number of Faeries you control. You choose one of those cards.
That player discards that card." (Thieving Sprite) - one CR 608.2c chain,
read whole because "those cards" and "it" point back across the periods.

CR 701.20a: to reveal a card is to show it to all players; the revealing
player chooses which X cards (the card is theirs to reveal, and the text
gives the choice to no one else), revealing their whole hand when it holds X
or fewer. The source's controller then chooses one of those (CR 608.2d).
The permission is CR 601.3's, lasting CR 611.2b's "for as long as" the
source stays under the caster's control (`PlayPermission.while_controlling`),
with CR 609.4b's "mana of any type can be spent" (`any_type_mana`).
"""

import re
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.player import Player
from ..numbers import parse_count
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_REVEAL_SOME_CHOOSE_ONE_RE = re.compile(
    r"^target (?:player|opponent) reveals (?:(?P<n>x|\w+) cards?|a number of cards) from their "
    r"hand(?:, where x is (?P<x_expr>.+?)| equal to (?P<eq_expr>.+?))?\.\s*"
    r"you choose one of (?:those|the revealed) cards\.\s*"
    r"(?:(?P<discard>that player discards (?:that card|it))|(?P<exile>that player exiles it))\.?"
    r"(?:\s*if an? (?P<quality>[a-z ]+?) card is exiled this way, you may cast it for as long as "
    r"you control this (?:creature|permanent)"
    r"(?P<any_type>, and mana of any type can be spent to cast (?:that spell|it))?\.?)?$",
    re.IGNORECASE,
)


def parse_reveal_some_then_choose_one(text: str) -> Any:
    """`_REVEAL_SOME_CHOOSE_ONE_RE`'s whole ability, or None."""
    match = _REVEAL_SOME_CHOOSE_ONE_RE.fullmatch(collapsed(text))
    if match is None:
        return None

    from .casting import PlayAction, once_per_turn_key
    from .effects import _nonland_or_typed_card_matcher, count_expression

    expression = match.group("x_expr") or match.group("eq_expr")
    fixed: int | None = None
    counter = None
    if expression is not None:
        counter = count_expression(expression)
        if counter is None:
            return None
    else:
        fixed = parse_count(match.group("n") or "")
        if fixed is None:
            return None
    to_exile = match.group("exile") is not None
    quality = match.group("quality")
    permits = None
    if quality is not None:
        if not to_exile:
            return None
        permits = _nonland_or_typed_card_matcher(quality)
        if permits is None:
            return None
    any_type_mana = match.group("any_type") is not None

    def effect(game: "Game", ability: Any) -> None:
        controller = game.controller_of(ability).username
        source = ability.source_name
        source_id = source_id_of(ability)
        revealer = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if revealer is None:
            return
        count = fixed if counter is None else counter(game, controller)
        hand = list(revealer.hand)
        if count is None or count <= 0 or not hand:
            return
        if len(hand) <= count:
            revealed = hand
        else:
            picked = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=revealer.username,
                    prompt=f"choose {count} card(s) from your hand to reveal for {source}",
                    source=source,
                    amount=count,
                    exact=True,
                    cards=tuple(card.id for card in hand),
                    source_id=source_id,
                )
            )
            by_id = {card.id: card for card in hand}
            revealed = [by_id[card_id] for card_id in picked]
        for card in revealed:
            game.reveal(card, source=source)
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose one of the cards {revealer.username} revealed",
                source=source,
                amount=1,
                exact=True,
                cards=tuple(card.id for card in revealed),
                source_id=source_id,
            )
        )
        chosen = next(card for card in revealed if card.id == chosen_ids[0])
        if not to_exile:
            game.discard_cards(revealer.username, [chosen], source=source)
            return
        exiled = game.exile_permanent(chosen)
        if permits is None or not isinstance(exiled, CardState) or not permits(exiled):
            return
        permanent = ability.source(game)
        if permanent is None:
            return
        game.grant_play_permission(
            exiled,
            controller,
            action=PlayAction.CAST,
            source_name=source,
            rule="CR 601.3, CR 611.2b",
            zone=exiled.zone,
            until_end_of_turn=False,
            any_type_mana=any_type_mana,
            while_controlling=once_per_turn_key(permanent),
        )

    return effect


# --------------------------------------------------------------------------
# R0a-T5: look at / reveal a hand, exile a card from it "until this creature
# leaves the battlefield" (CR 610.3) - Deep-Cavern Bat, Kitesail Freebooter
# --------------------------------------------------------------------------

_HAND_EXILE_UNTIL_LEAVES_RE = re.compile(
    r"^(?:look at target (?:opponent|player)'s hand|target (?:opponent|player) reveals their "
    r"hand)\.\s*you (?P<may>may )?(?P<verb>exile|choose) an? (?P<quality>[a-z, ]+?) card from it"
    r"(?P<then>\.\s*exile that card)? until this (?:creature|artifact|enchantment|permanent) "
    r"leaves the battlefield\.?$",
    re.IGNORECASE,
)


def parse_hand_exile_until_leaves_clause(text: str) -> Any:
    """`_HAND_EXILE_UNTIL_LEAVES_RE`'s effect: the targeted player's hand is
    seen (CR 701.20a for "reveals"; "look at" shows it only to the
    controller), the controller chooses a card of that quality - optionally
    for "you may" - and it is exiled until the source leaves the battlefield,
    then returned to its owner's hand (CR 610.3's "previous zone"). CR 610.3b:
    if the source already left before this resolved, nothing is exiled."""
    match = _HAND_EXILE_UNTIL_LEAVES_RE.fullmatch(collapsed(text))
    if match is None:
        return None

    from .effects import _nonland_or_typed_card_matcher

    if (match.group("verb").lower() == "choose") != (match.group("then") is not None):
        return None
    permits = _nonland_or_typed_card_matcher(match.group("quality").strip())
    if permits is None:
        return None
    optional = match.group("may") is not None

    def effect(game: "Game", ability: Any) -> None:
        from ..models.zone import Zone
        from .effects import _watch_for_departure_and_return_exiled_card

        players = [target for target in game.resolve_targets(ability) if isinstance(target, Player)]
        source = ability.source(game)
        if not players or source is None or source.zone is not Zone.BATTLEFIELD:
            return
        victim = players[0]
        candidates = [card for card in victim.hand if permits(card)]
        if not candidates:
            return
        if optional and not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=ability.controller,
                prompt=f"exile a card from {victim.username}'s hand",
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=True,
            )
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=ability.controller,
                prompt=f"choose a card from {victim.username}'s hand to exile",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(card.id for card in candidates),
            )
        )
        by_id = {card.id: card for card in candidates}
        for chosen_id in chosen_ids or ():
            card = by_id.get(chosen_id)
            if card is None or card.zone is not Zone.HAND:
                continue
            victim.cards_in(Zone.HAND).remove(card)
            card.move_to(Zone.EXILE)
            game.exile.append(card)
            _watch_for_departure_and_return_exiled_card(
                game, source, card, ability.controller, return_zone=Zone.HAND
            )

    return effect
