"""EP-02 R2 T4: the power, toughness or mana value of a referenced permanent or
card, spent as an amount the earlier readers do not reach.

"Its controller gains life equal to its toughness" (Condemn), "scry X, where X
is its power" (Spotter Thopter), "look at the top X cards of your library,
where X is that creature's power" (Cream of the Crop, Keldon Flamesage,
Radagast the Brown), "each opponent loses life equal to the sacrificed
creature's power" (Xathrid Demon), "~ deals X damage ... and you gain X life,
where X is the sacrificed permanent's mana value" (Ayara), "destroy target
artifact. This creature gets +X/+0, where X is that artifact's mana value"
(Hoard-Smelter Dragon), and the card/spell mana value texts T3's reader
(`ep02_r2_card_mana_value`) was built for.

One compiler, `referenced_permanent_stat_effect`, turns the sentences of a text
into resolution steps run in order (CR 608.2c) over the `RunState` T3 defined:
an opener fixes the object the amount names before it moves (CR 608.2h - the
characteristic is taken once, as the effect applies, from the object as it last
existed, CR 603.10a), and later sentences spend it. It reads every sentence
through the established readers first: `ep02_r1_moved_card_stat` for the
amounts and openers it owns, `ep02_r2_card_mana_value` for the card openers
(reveal, mill, discard at random).  What this module adds is only what none of
them reach.

A negative characteristic counts as zero (CR 107.1b).
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState
from ..models.mana import ManaCost
from ..models.player import Player
from ..models.zone import Zone
from .amount_sentences import (
    apply_life,
    parse_life_clause,
    split_where_x,
)
from .ep02_r1_moved_card_stat import (
    _IF_YOU_DO_RE,
    Moved,
    Phrase,
    ResolutionStep,
    State,
    _amount_step,
    _clean,
    _referent_for,
    _step_stat_sized_token,
    card_snapshot,
    moved_stat_value,
    parse_moved_phrase,
)
from .ep02_r2_card_mana_value import (
    RunState,
    _bottom,
    _card_of,
    _name_and_id,
    _opener,
    _step_cast_free,
    _step_put_in_hand,
    _unwrap_then,
)

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# The amount phrase
# --------------------------------------------------------------------------

_SELF_STAT_RE = re.compile(
    r"^this (?:creature|permanent|artifact)'s (?P<stat>power|toughness|mana value)$"
)


@functools.cache
def parse_ref(phrase: str) -> Phrase | None:
    """ "this creature's power" (the source itself, anchor "self") or any
    phrase `parse_moved_phrase` reads ("its power", "that creature's power",
    "that artifact's mana value", "the sacrificed permanent's mana value")."""
    text = " ".join(phrase.replace("’", "'").split()).rstrip(".").lower()
    if (match := _SELF_STAT_RE.fullmatch(text)) is not None:
        return Phrase("self", match.group("stat"))
    return parse_moved_phrase(text)


def referent_of(game: "Game", stack_object: Any, state: State, phrase: Phrase) -> Any:
    """The object `phrase` names: the source for "this creature's", else what
    an earlier sentence fixed, what the cost paid, or the trigger's subject."""
    if phrase.anchor == "self":
        source = _source(game, stack_object)
        return None if source is None else card_snapshot(game, source)
    return _referent_for(game, stack_object, state, phrase.anchor)


def stat_value(game: "Game", stack_object: Any, state: State, phrase: Phrase) -> int:
    """The characteristic `phrase` names, never negative (CR 107.1b)."""
    return moved_stat_value(referent_of(game, stack_object, state, phrase), phrase.stat)


def _source(game: "Game", stack_object: Any) -> CardState | None:
    if isinstance(stack_object, CardState):
        return stack_object
    return stack_object.source_or_last_known(game)


# --------------------------------------------------------------------------
# The run state
# --------------------------------------------------------------------------


@dataclass
class Run(RunState):
    """`RunState` plus the player a sentence chose a card from."""

    looked: list[CardState] = field(default_factory=list)


# --------------------------------------------------------------------------
# Openers
# --------------------------------------------------------------------------

#: What "its / that card's mana value" reads when the opening sentence found no
#: card (an empty library or graveyard, a declined payment): nothing, which has
#: no characteristics - so the amount is 0 (CR 107.1b) and no kind matches.
NO_CARD = Moved(
    card_id=UUID(int=0),
    power=0,
    toughness=0,
    mana_value=0,
    types=frozenset(),
    subtypes=frozenset(),
)

_DESTROY_TARGET_RE = re.compile(r"^destroy target (?P<what>[a-z ]+?)$", re.IGNORECASE)
_PUT_BOTTOM_RE = re.compile(
    r"^put target (?P<what>[a-z ]+?) on the bottom of its owner's library$", re.IGNORECASE
)
_CLASH_RE = re.compile(r"^clash with an opponent$", re.IGNORECASE)
_SACRIFICE_THEN_RE = re.compile(
    r"^(?P<who>target player |target opponent )?(?P<may>you may )?sacrifices? "
    r"(?P<restriction>(?:an?|another) [a-z ]+?)"
    r"(?P<saddled> that saddled (?:it|this creature) this turn)?"
    r"(?P<other> other than this creature)?"
    r"(?: of their choice)?(?:,? then (?P<rest>.+))?$",
    re.IGNORECASE,
)
_REVEAL_HAND_RE = re.compile(r"^target opponent reveals their hand$", re.IGNORECASE)
_CHOOSE_FROM_HAND_RE = re.compile(r"^you choose an? (?P<quality>.+?) card from it$", re.IGNORECASE)
_DISCARD_CHOSEN_RE = re.compile(r"^that player discards that card$", re.IGNORECASE)


def _step_put_on_bottom(game: "Game", stack_object: Any, state: State) -> bool:
    target = state.next_target(game, stack_object)
    if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return True
    state.referent = card_snapshot(game, target)  # CR 608.2h: before it leaves
    game.put_cards_into_library([target], to_bottom=True)
    state.did = target.zone is Zone.LIBRARY
    return True


def _step_clash(game: "Game", stack_object: Any, state: State) -> bool:
    from .legacy_keywords import clash

    name, source_id = _name_and_id(stack_object)
    state.did = clash(game, game.controller_of(stack_object), source=name, source_id=source_id)
    return True


def _step_sacrifice_choice(
    restriction_text: str,
    *,
    who: str,
    may: bool,
    saddled: bool,
    not_self: bool,
    for_spell: bool,
) -> ResolutionStep | None:
    """ "[Target player] [you may] sacrifice[s] a creature [that saddled it this
    turn | other than this creature]": the player chooses among their own
    permanents (CR 701.21a), the permanent is read before it goes (CR 608.2h),
    and the verdict is remembered for "if you do" / "if you can't"."""
    from .decisions import Decision, DecisionKind, source_id_of
    from .effects._common import _permanent_id_and_name
    from .effects.modal import _choose_permanents_to_sacrifice
    from .effects.removal import _sacrifice_is_payable, _sacrifice_restriction

    restriction = _sacrifice_restriction(restriction_text)
    if restriction is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        if who:
            # The text's "that player" reads back to this same target.
            chosen_player = state.first_target(game, stack_object)
            if not isinstance(chosen_player, Player):
                return False
            player = chosen_player
            state.player = player.username
        else:
            player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = restriction.candidates(game, player, source_id)
        source = _source(game, stack_object)
        if saddled and source is not None:
            candidates = [c for c in candidates if c.id in source.saddled_by]
        if not_self:
            candidates = [c for c in candidates if c.id != source_id]
        state.did = False
        if may:
            decision = Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=f"sacrifice {restriction_text.strip()}",
                source=source_name,
                affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
                source_id=source_id_of(stack_object),
            )
            if not game.ask(decision):
                return False
        if not candidates:
            return True
        chosen = _choose_permanents_to_sacrifice(
            game,
            player,
            restriction,
            candidates,
            source_name=source_name,
            source_id=source_id_of(stack_object),
        )
        if len(chosen) != 1:
            return True
        state.referent = card_snapshot(game, chosen[0])
        game.sacrifice(chosen[0])
        state.did = chosen[0].zone is not Zone.BATTLEFIELD
        return True

    return step


def _step_reveal_hand(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    target = state.next_target(game, stack_object)
    if not isinstance(target, Player):
        return False
    state.player = target.username
    name, _ = _name_and_id(stack_object)
    for card in list(target.hand):
        game.reveal(card, source=name)
    return True


def _step_choose_from_hand(quality: str) -> ResolutionStep | None:
    from .decisions import Decision, DecisionKind
    from .effects._common import _quality_matcher

    matches = _quality_matcher(quality)

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        if state.player is None:
            return False
        name, source_id = _name_and_id(stack_object)
        hand = game.player(state.player).hand
        options = [card for card in hand if matches(card)]
        state.did = False
        if not options:
            return True
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=game.controller_of(stack_object).username,
                prompt=f"choose {quality} card from the revealed hand",
                source=name,
                source_id=source_id,
                amount=1,
                cards=tuple(card.id for card in options),
            )
        )
        card = next(card for card in options if card.id == chosen_ids[0])
        state.card = card
        state.referent = card_snapshot(game, card)
        state.did = True
        return True

    return step


def _step_discard_chosen(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    if state.card is None or state.player is None or state.card.zone is not Zone.HAND:
        return True
    name, _ = _name_and_id(stack_object)
    game.discard_cards(state.player, [state.card], source=name)
    return True


_EXILE_TOP_CARD_RE = re.compile(r"^exile the top card of your library$", re.IGNORECASE)
_EXILE_UNTIL_NONLAND_RE = re.compile(
    r"^exile cards from the top of your library until you exile a nonland card$", re.IGNORECASE
)
_PAY_AND_DISCARD_RE = re.compile(
    r"^you may pay (?P<cost>(?:\{[^}]+\})+) and discard a card$", re.IGNORECASE
)
_EXILE_PERMANENT_FROM_GRAVEYARD_RE = re.compile(
    r"^exile a permanent card from your graveyard$", re.IGNORECASE
)
_TURN_UP_RE = re.compile(r"^turn the exiled card face up$", re.IGNORECASE)
_CONTROLLER_SACRIFICES_IT_RE = re.compile(
    r"^target creature's controller sacrifices it(?:,? then (?P<rest>.+))?$", re.IGNORECASE
)
_THAT_PLAYER_CREATES_RE = re.compile(
    r"^that player creates (?P<what>an? .+? tokens?(?: with .+)?)$", re.IGNORECASE
)


def _step_exile_top_card(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Exile the top card of your library." (CR 701.13a): the card the next
    sentences call "that card" / "the exiled card", read as it is in exile
    (CR 608.2h). An empty library exiles nothing."""
    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    state.card, state.referent, state.did = None, NO_CARD, False
    if player.library:
        top = player.library[0]
        game.exile_permanent(top)
        if top.zone is Zone.EXILE:
            state.card, state.referent, state.did = top, card_snapshot(game, top), True
    return True


def _step_exile_until_nonland(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Exile cards from the top of your library until you exile a nonland
    card." (CR 701.13a): each card goes to exile in turn; the nonland one is
    "that card". A library of lands is exiled whole and leaves no card."""
    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    state.card, state.referent, state.did = None, NO_CARD, False
    for card in list(player.library):
        game.exile_permanent(card)
        if not card.card.is_land and card.zone is Zone.EXILE:
            state.card, state.referent, state.did = card, card_snapshot(game, card), True
            break
    return True


def _step_pay_and_discard(cost: ManaCost) -> ResolutionStep:
    """ "You may pay {cost} and discard a card" (CR 608.2c, CR 701.9a): the
    payment is made first, then the player picks the card to discard; the card
    is "the discarded card", with the mana value it had in hand (CR 608.2h).
    Both parts are one optional action, so it is not offered with an empty
    hand."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        player = game.controller_of(stack_object)
        name, source_id = _name_and_id(stack_object)
        state.did, state.card, state.referent = False, None, NO_CARD
        if not player.hand:
            return True
        if not game.may_pay_mana_cost(player, cost, source=name, source_id=source_id):
            return True
        chosen = _choose_among(
            game,
            player,
            list(player.hand),
            "choose a card to discard",
            required=True,
            name=name,
            source_id=source_id,
        )
        if chosen is None:
            return True
        snapshot = card_snapshot(game, chosen)
        game.discard_cards(player.username, [chosen], source=name)
        if chosen.zone is Zone.GRAVEYARD:
            state.card, state.referent, state.did = chosen, snapshot, True
        return True

    return step


_PERMANENT_CARD_TYPES = frozenset(
    {Type.ARTIFACT, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER, Type.BATTLE}
)


def _step_exile_permanent_from_graveyard(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Exile a permanent card from your graveyard." (CR 608.2d: the player
    chooses): the card is exiled *with* the ability's source, the link the
    source's other abilities read back (CR 607.2a)."""
    from .exile_top_marked import mark_exiled

    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    name, source_id = _name_and_id(stack_object)
    state.card, state.referent, state.did = None, NO_CARD, False
    options = [card for card in player.graveyard if _PERMANENT_CARD_TYPES & set(card.types)]
    chosen = _choose_among(
        game,
        player,
        options,
        "exile a permanent card from your graveyard",
        required=True,
        name=name,
        source_id=source_id,
    )
    if chosen is None:
        return True
    (moved,) = game.exile_cards([chosen])
    if moved.zone is Zone.EXILE:
        mark_exiled(game, stack_object, moved)
        state.card, state.referent, state.did = moved, card_snapshot(game, moved), True
    return True


def _step_load_exiled_card(game: "Game", stack_object: Any, state: State) -> bool:
    """ "The exiled card" of a later chapter or ability: the card the source's
    earlier ability exiled and linked to it (CR 607.2a)."""
    from .exiled_with_peek import _pile

    assert isinstance(state, RunState)
    if getattr(stack_object, "source_id", None) is None:
        return True
    pile = _pile(game, stack_object)
    state.card, state.referent = (
        (pile[-1], card_snapshot(game, pile[-1])) if pile else (None, NO_CARD)
    )
    return True


def _step_turn_exiled_face_up(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Turn the exiled card face up." (CR 406.3a): it now has its
    characteristics, which the next sentences read."""
    _step_load_exiled_card(game, stack_object, state)
    assert isinstance(state, RunState)
    if state.card is not None and state.card.zone is Zone.EXILE:
        state.card.face_up = True
        state.referent = card_snapshot(game, state.card)
    return True


def _step_return_source_and_card(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Return this Saga and the exiled card to their owner's hand."""
    assert isinstance(state, RunState)
    source = _source(game, stack_object)
    if source is not None and source.zone is Zone.BATTLEFIELD:
        game.return_to_hand(source)
    if state.card is not None and state.card.zone is Zone.EXILE:
        game.return_to_hand(state.card)
    return True


def _step_return_exiled_to_hand(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    if state.card is not None and state.card.zone is Zone.EXILE:
        game.return_to_hand(state.card)
    return True


def _step_may_put_exiled_onto_battlefield(kind: str | None) -> ResolutionStep:
    """ "You may put the exiled card onto the battlefield[ if it's a <kind>
    card]": the offer is made only for a card of that kind, and what was done
    is remembered for the "if you don't" that follows."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        card = state.card
        state.did = False
        if card is None or card.zone is not Zone.EXILE:
            return True
        if kind is not None and (state.referent is None or not state.referent.is_a(kind)):
            return True
        name, source_id = _name_and_id(stack_object)
        if not game.may(
            game.controller_of(stack_object),
            f"put {card.name} onto the battlefield",
            source=name,
            source_id=source_id,
        ):
            return True
        game.put_onto_battlefield(card, game.controller_of(stack_object).username)
        state.did = card.zone is Zone.BATTLEFIELD
        return True

    return step


def _step_play_exiled_card(game: "Game", stack_object: Any, state: State) -> bool:
    """ "You may play that card until end of turn." (CR 601.3, CR 305.1)."""
    from .casting import PlayAction

    assert isinstance(state, RunState)
    card = state.card
    if card is not None and card.zone is Zone.EXILE:
        name, _ = _name_and_id(stack_object)
        game.grant_play_permission(
            card,
            game.controller_of(stack_object).username,
            action=PlayAction.PLAY,
            source_name=name or "",
            zone=Zone.EXILE,
            until_end_of_turn=True,
        )
    return True


def _step_then_creates(what: str) -> ResolutionStep | None:
    """ "...then that player creates a 5/5 red Dragon creature token with
    flying": the token's creator is the controller of the sacrificed permanent
    (CR 111.2)."""
    from .amount_sentences import token_maker

    make = token_maker(what)
    if make is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        make(game, state.token_controller or game.controller_of(stack_object).username, 1)
        return True

    return step


def _extra_opener(sentence: str, *, for_spell: bool) -> tuple[ResolutionStep, str | None] | None:
    """`(step, tail)` for the openers that none of the earlier readers read."""
    if _EXILE_TOP_CARD_RE.fullmatch(sentence):
        return _step_exile_top_card, None
    if _EXILE_UNTIL_NONLAND_RE.fullmatch(sentence):
        return _step_exile_until_nonland, None
    if (match := _PAY_AND_DISCARD_RE.fullmatch(sentence)) is not None:
        return _step_pay_and_discard(ManaCost.parse(match.group("cost"))), None
    if _EXILE_PERMANENT_FROM_GRAVEYARD_RE.fullmatch(sentence):
        return _step_exile_permanent_from_graveyard, None
    if _TURN_UP_RE.fullmatch(sentence):
        return _step_turn_exiled_face_up, None
    if (match := _DESTROY_TARGET_RE.fullmatch(sentence)) is not None:
        from .ep02_r1_moved_card_stat import _step_delegate_to_target

        step = _step_delegate_to_target(f"{sentence}.", for_spell=for_spell)
        return None if step is None else (step, None)
    if _PUT_BOTTOM_RE.fullmatch(sentence):
        return _step_put_on_bottom, None
    if _CLASH_RE.fullmatch(sentence):
        return _step_clash, None
    if _REVEAL_HAND_RE.fullmatch(sentence):
        return _step_reveal_hand, None
    if (match := _CHOOSE_FROM_HAND_RE.fullmatch(sentence)) is not None:
        step = _step_choose_from_hand(match.group("quality"))
        return None if step is None else (step, None)
    if (match := _SACRIFICE_THEN_RE.fullmatch(sentence)) is not None:
        restriction = match.group("restriction").strip()
        if match.group("other"):
            restriction = "another " + restriction.split(" ", 1)[1]
        step = _step_sacrifice_choice(
            restriction,
            who=(match.group("who") or "").strip(),
            may=bool(match.group("may")),
            saddled=bool(match.group("saddled")),
            not_self=bool(match.group("other")),
            for_spell=for_spell,
        )
        return None if step is None else (step, match.group("rest"))
    return None


# --------------------------------------------------------------------------
# Sentences that spend an amount
# --------------------------------------------------------------------------

_SCRY_X_RE = re.compile(r"^scry x$", re.IGNORECASE)
_X_DAMAGE_LIFE_RE = re.compile(
    r"^(?P<source>.+?) deals x damage to (?P<to>target [a-z ]+?)"
    r" and you gain x life$",
    re.IGNORECASE,
)
_ITS_CONTROLLER_RE = re.compile(r"^its controller$", re.IGNORECASE)
_DELAYED_SACRIFICE_RE = re.compile(
    r"^sacrifice (?P<what>it|this artifact|this permanent|this creature) "
    r"at the beginning of the next end step$",
    re.IGNORECASE,
)
_TAP_THIS_RE = re.compile(r"^tap this (?:creature|permanent)$", re.IGNORECASE)
_DRAW_THEN_LANDS_RE = re.compile(
    r"^draw x cards, then put up to x land cards from your hand onto the battlefield tapped$",
    re.IGNORECASE,
)


def _step_scry_x(phrase: Phrase) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = stat_value(game, stack_object, state, phrase)
        name, source_id = _name_and_id(stack_object)
        if amount > 0:
            game.scry(game.controller_of(stack_object), amount, source=name, source_id=source_id)
        return True

    return step


def _step_damage_and_life(source: str, phrase: Phrase) -> ResolutionStep:
    """ "<Source> deals X damage to <target> and you gain X life, where X is
    the stat": one amount, read once (CR 608.2h), both parts in order."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = stat_value(game, stack_object, state, phrase)
        target = state.next_target(game, stack_object)
        card = _source(game, stack_object)
        if target is not None:
            game.deal_damage(target, amount, source=card)
        apply_life(game, stack_object, "you", True, lambda *_: amount)
        return True

    return step


def _step_life_to_controller(gains: bool, phrase: Phrase) -> ResolutionStep:
    """ "Its controller gains life equal to its toughness": the controller of
    the object the amount names, as it last was (CR 603.10a)."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        referent = referent_of(game, stack_object, state, phrase)
        amount = moved_stat_value(referent, phrase.stat)
        owner = getattr(referent, "controller", None)
        if owner is not None:
            apply_life(
                game, stack_object, "that player", gains, lambda *_: amount, fallback=(owner,)
            )
        return True

    return step


def _step_delayed_sacrifice(what: str) -> ResolutionStep:
    """ "Sacrifice it / this artifact at the beginning of the next end step."
    (CR 603.7): a delayed trigger about that one object (CR 603.7c)."""
    from .abilities import TriggerEvent
    from .delayed import DelayedTrigger, sacrifice_subject
    from .turn import Step

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        if what.lower() == "it":
            subject = state.first_target(game, stack_object)
            if not isinstance(subject, CardState):
                subject = _card_of(game, state) if isinstance(state, RunState) else None
        else:
            subject = _source(game, stack_object)
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return True
        is_spell = isinstance(stack_object, CardState)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=f"Sacrifice {what} at the beginning of the next end step.",
                effect=sacrifice_subject,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=game.controller_of(stack_object).username,
                source_id=stack_object.id if is_spell else stack_object.source_id,
                source_name=stack_object.name if is_spell else stack_object.source_name,
                subject_id=subject.id,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=subject.zone_change_stamp,
            )
        )
        return True

    return step


def _step_plain(sentence: str, *, for_spell: bool) -> ResolutionStep | None:
    """A sentence naming no referenced amount ("tap this creature", "you lose 7
    life"), run by the established clause readers."""
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell

    effect = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(f"{sentence}.")
    if effect is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        effect(game, stack_object)
        return True

    return step


def _step_tap_source(game: "Game", stack_object: Any, state: State) -> bool:
    source = _source(game, stack_object)
    if source is not None and source.zone is Zone.BATTLEFIELD:
        game.tap_permanent(source)
    return True


def _step_draw_then_lands(phrase: Phrase) -> ResolutionStep:
    """ "Draw X cards, then put up to X land cards from your hand onto the
    battlefield tapped, where X is the stat" (CR 608.2c: in order, the lands
    chosen from the hand after the draw)."""
    from .decisions import Decision, DecisionKind

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = stat_value(game, stack_object, state, phrase)
        player = game.controller_of(stack_object)
        name, source_id = _name_and_id(stack_object)
        game.draw_cards(player, amount)
        lands = [card for card in player.hand if card.card.is_land]
        if amount <= 0 or not lands:
            return True
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"put up to {amount} land cards onto the battlefield tapped",
                source=name,
                source_id=source_id,
                amount=min(amount, len(lands)),
                exact=False,
                cards=tuple(card.id for card in lands),
            )
        )
        by_id = {card.id: card for card in lands}
        for card_id in list(chosen_ids)[:amount]:
            if (card := by_id.get(card_id)) is not None and card.zone is Zone.HAND:
                game.put_onto_battlefield(card, player.username, tapped=True)
        return True

    return step


_BITE_RE = re.compile(
    r"^(?P<dealer>it|that creature|this creature) deals damage equal to its power to "
    r"(?P<to>target [a-z ]+?|this creature|that creature)$",
    re.IGNORECASE,
)
_ON_BATTLEFIELD_RE = re.compile(
    r"^if this creature is on the battlefield,? (?P<rest>.+)$", re.IGNORECASE
)
_COPY_TOKEN_RE = re.compile(
    r"^create a token that'?s a copy of (?:that card|it), except (?P<exception>.+)$", re.IGNORECASE
)
_SIZED_TOKEN_RE = re.compile(
    r"^create an? (?P<desc>.+?) tokens? with power equal to (?P<power>.+?) "
    r"and toughness equal to (?P<toughness>.+)$",
    re.IGNORECASE,
)


def _step_bite(dealer: str, recipient: str) -> ResolutionStep:
    """ "<It | That creature> deals damage equal to its power to <recipient>":
    the dealer's own power, as it is (CR 613.5) or as it last was (CR 608.2h)
    if it has since left."""

    def object_named(game: "Game", stack_object: Any, state: State, word: str) -> Any:
        if word.lower() in ("it", "this creature"):
            return _source(game, stack_object)
        return state.first_target(game, stack_object)

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        source = object_named(game, stack_object, state, dealer)
        if not isinstance(source, CardState):
            return True
        amount = moved_stat_value(card_snapshot(game, source), "power")
        if recipient.lower() in ("this creature", "that creature"):
            target = object_named(game, stack_object, state, recipient)
        else:
            target = state.next_target(game, stack_object)
        if target is not None:
            game.deal_damage(target, amount, source=source)
        return True

    return step


def _step_guard_source_on_battlefield(inner: ResolutionStep) -> ResolutionStep:
    """ "If this creature is on the battlefield, <inner>" (CR 608.2b)."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        source = _source(game, stack_object)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return True
        return inner(game, stack_object, state)

    return step


def _step_copy_token(exception: str) -> ResolutionStep | None:
    """ "Create a token that's a copy of that card, except <exception>" (CR 707.2,
    CR 707.9a, CR 707.9b): the copy is of the card an earlier sentence moved, read as the
    card it is where it went."""
    from ..models.token import token_copy_of
    from .effects.tokens import (
        _read_copy_exception_list,
        _read_token_copy_except,
        _read_token_copy_replacing_except,
    )

    replacing = _read_token_copy_replacing_except(exception)
    listed = _read_copy_exception_list(exception)
    options: dict[str, Any]
    if replacing is not None:
        power, toughness, colors, creature_types = replacing
        options = {
            "power": power,
            "toughness": toughness,
            "colors": colors,
            "creature_types": creature_types,
        }
    elif listed is not None:
        options = {
            "added_abilities": listed.added_abilities,
            "power": listed.power,
            "toughness": listed.toughness,
            "added_creature_type": listed.added_creature_type,
            "not_legendary": listed.not_legendary,
        }
    else:
        read = _read_token_copy_except(exception)
        if read is None:
            return None
        added, power, toughness, added_type = read
        options = {
            "added_abilities": added,
            "power": power,
            "toughness": toughness,
            "added_creature_type": added_type,
        }

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        referent = state.referent
        original = None if referent is None else game.find_by_id(referent.card_id)
        if isinstance(original, CardState):
            token_copy_of(game, original, game.controller_of(stack_object).username, **options)
        return True

    return step


_SELF_DAMAGE_RE = re.compile(
    r"^(?P<source>.+?) deals damage to (?:himself|herself|itself|themselves) equal to "
    r"(?P<expr>.+)$",
    re.IGNORECASE,
)
_MAY_HAVE_DEAL_RE = re.compile(
    r"^you may have (?P<source>.+?) deal damage to (?P<to>that [a-z ]+) equal to (?P<expr>.+)$",
    re.IGNORECASE,
)
_BECOMES_XX_RE = re.compile(r"^(?P<head>.+? becomes an? )x/x(?P<tail> .+)$", re.IGNORECASE)
_HIGHEST_LIFE_TOKENS_RE = re.compile(
    r"^create a number of (?P<what>.+?) equal to the highest life total among all players$",
    re.IGNORECASE,
)
_EACH_DEALS_POWER_RE = re.compile(
    r"^each (?P<quality>[a-z ]+?) you control deals damage equal to its power to "
    r"(?P<to>target [a-z ]+?)$",
    re.IGNORECASE,
)
_PLAY_THAT_CARD_RE = re.compile(
    r"^you may play (?:that|the exiled) card (?:until end of turn|this turn)$", re.IGNORECASE
)
_RETURN_SOURCE_AND_CARD_RE = re.compile(
    r"^return this [a-z]+ and the exiled card to their owner's hand$", re.IGNORECASE
)
_RETURN_EXILED_RE = re.compile(r"^put it into its owner's hand$", re.IGNORECASE)
_MAY_PUT_EXILED_RE = re.compile(
    r"^you may put (?:the exiled card|it|that card) onto the battlefield"
    r"(?: if it's an? (?P<kind>[a-z]+) card)?$",
    re.IGNORECASE,
)


def _step_may_deal_damage(phrase: Phrase) -> ResolutionStep:
    """ "You may have <source> deal damage to that creature equal to <stat>":
    declining is remembered for the "if you don't" that follows."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        name, source_id = _name_and_id(stack_object)
        state.did = False
        if not game.may(
            game.controller_of(stack_object),
            f"have {name} deal the damage",
            source=name,
            source_id=source_id,
        ):
            return True
        amount = stat_value(game, stack_object, state, phrase)
        target = state.first_target(game, stack_object)
        if target is not None:
            game.deal_damage(target, amount, source=_source(game, stack_object))
            state.did = True
        return True

    return step


def _step_damage_to_self(phrase: Phrase) -> ResolutionStep:
    """ "<It> deals damage to itself equal to <stat>": the source is both the
    dealer and the recipient (CR 120.3)."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = stat_value(game, stack_object, state, phrase)
        source = _source(game, stack_object)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.deal_damage(source, amount, source=source)
        return True

    return step


def _step_rewrite_with_value(head: str, tail: str, phrase: Phrase) -> ResolutionStep | None:
    """ "<head>X/X<tail>, where X is <stat>": the continuous effect the layer
    engine reads off the sentence with the stat written in (CR 608.2h: counted
    once, as the effect applies; CR 611.2 the effect it creates)."""
    from .effects import continuous_effects, layer_context_for
    from .effects.text import _as_sentence
    from .targeting import profile_for_text

    def text_for(value: int) -> str:
        return _as_sentence(f"{head}{value}/{value}{tail}")

    profile = profile_for_text(text_for(1))
    if not profile.understood:
        return None
    needs_target = bool(profile.requirements)

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        source = _source(game, stack_object)
        if source is None:
            return True
        if needs_target:
            targets = game.resolve_card_targets(stack_object)
        else:
            targets = [source] if source.zone is Zone.BATTLEFIELD else []
        if targets:
            continuous_effects(game).create(
                source,
                targets=targets,
                context=layer_context_for(game, game.controller_of(stack_object)),
                ability_text=text_for(stat_value(game, stack_object, state, phrase)),
                game=game,
            )
        return True

    return step


def _step_highest_life_tokens(what: str) -> ResolutionStep | None:
    """ "Create a number of <tokens> equal to the highest life total among all
    players": the total is read once (CR 608.2h), as the effect applies."""
    from .amount_sentences import token_maker

    make = token_maker(f"X {what}")
    if make is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        highest = max((player.life for player in game.players_in_game), default=0)
        make(game, game.controller_of(stack_object).username, highest)
        return True

    return step


def _step_each_deals_power(quality: str) -> ResolutionStep | None:
    """ "Each <Dragon creature> you control deals damage equal to its power to
    <target>": every matching permanent deals its own power (CR 613.5), each
    amount read as the effect applies (CR 608.2h)."""
    words = quality.lower().split()
    types = {Type(word) for word in words if word in {t.value for t in Type}}
    subtypes = {word for word in words if word not in {t.value for t in Type}}
    if not types and not subtypes:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        target = state.next_target(game, stack_object)
        dealers = []
        for permanent in game.permanents_controlled_by(game.controller_of(stack_object).username):
            chars = game.characteristics_of(permanent)
            if types <= set(chars.types) and subtypes <= {s.lower() for s in chars.subtypes}:
                dealers.append((permanent, max(chars.power or 0, 0)))
        if target is not None:
            for permanent, amount in dealers:
                game.deal_damage(target, amount, source=permanent)
        return True

    return step


def _conditioned(step: ResolutionStep, condition: str) -> ResolutionStep:
    """ "If you control <N> or more <things>, ...": the board condition is
    checked as the instruction is reached (CR 608.2c)."""

    def conditioned(game: "Game", stack_object: Any, state: State) -> bool:
        holds = game.condition_holds(
            game.controller_of(stack_object).username, condition, _source(game, stack_object)
        )
        return step(game, stack_object, state) if holds else True

    return conditioned


def _extra_step(sentence: str, *, for_spell: bool) -> ResolutionStep | None:
    """The amount sentences (and the plain sentences between them) that none
    of the earlier readers read."""
    where = split_where_x(sentence)
    body, tail = where if where is not None else (sentence, "")
    phrase = parse_ref(tail) if where is not None else None
    if phrase is not None:
        if _SCRY_X_RE.fullmatch(body):
            return _step_scry_x(phrase)
        if (match := _X_DAMAGE_LIFE_RE.fullmatch(body)) is not None:
            return _step_damage_and_life(match.group("source"), phrase)
        if _DRAW_THEN_LANDS_RE.fullmatch(body):
            return _step_draw_then_lands(phrase)
        if (match := _BECOMES_XX_RE.fullmatch(body)) is not None:
            return _step_rewrite_with_value(match.group("head"), match.group("tail"), phrase)
    if (life := parse_life_clause(sentence)) is not None and life.kind == "equal":
        phrase = parse_ref(life.expr or "")
        if phrase is not None and _ITS_CONTROLLER_RE.fullmatch(life.subject or ""):
            return _step_life_to_controller(life.gains, phrase)
    if (match := _DELAYED_SACRIFICE_RE.fullmatch(sentence)) is not None:
        return _step_delayed_sacrifice(match.group("what"))
    if (match := _MAY_HAVE_DEAL_RE.fullmatch(sentence)) is not None:
        phrase = parse_ref(match.group("expr"))
        return None if phrase is None else _step_may_deal_damage(phrase)
    if (match := _SELF_DAMAGE_RE.fullmatch(sentence)) is not None:
        phrase = parse_ref(match.group("expr"))
        return None if phrase is None else _step_damage_to_self(phrase)
    if (match := _HIGHEST_LIFE_TOKENS_RE.fullmatch(sentence)) is not None:
        return _step_highest_life_tokens(match.group("what"))
    if (match := _EACH_DEALS_POWER_RE.fullmatch(sentence)) is not None:
        return _step_each_deals_power(match.group("quality"))
    if (match := _THAT_PLAYER_CREATES_RE.fullmatch(sentence)) is not None:
        return _step_then_creates(match.group("what"))
    if _PLAY_THAT_CARD_RE.fullmatch(sentence):
        return _step_play_exiled_card
    if _RETURN_SOURCE_AND_CARD_RE.fullmatch(sentence):
        return _step_return_source_and_card
    if _RETURN_EXILED_RE.fullmatch(sentence):
        return _step_return_exiled_to_hand
    if (match := _MAY_PUT_EXILED_RE.fullmatch(sentence)) is not None:
        return _step_may_put_exiled_onto_battlefield(match.group("kind"))
    if _DISCARD_CHOSEN_RE.fullmatch(sentence):
        return _step_discard_chosen
    if _PUT_IT_IN_HAND_RE.fullmatch(sentence):
        return _step_put_in_hand
    if _TAP_THIS_RE.fullmatch(sentence):
        return _step_tap_source
    if (match := _BITE_RE.fullmatch(sentence)) is not None:
        return _step_bite(match.group("dealer"), match.group("to"))
    if (match := _ON_BATTLEFIELD_RE.fullmatch(sentence)) is not None:
        inner = _extra_step(match.group("rest"), for_spell=for_spell)
        return None if inner is None else _step_guard_source_on_battlefield(inner)
    if (match := _COPY_TOKEN_RE.fullmatch(sentence)) is not None:
        return _step_copy_token(match.group("exception"))
    if (match := _SIZED_TOKEN_RE.fullmatch(sentence)) is not None:
        power, toughness = parse_ref(match.group("power")), parse_ref(match.group("toughness"))
        if power is None or toughness is None:
            return None
        return _step_stat_sized_token(match.group("desc"), (power, toughness))
    return None


# --------------------------------------------------------------------------
# "Look at the top X cards of your library, where X is <stat>" and what follows
# --------------------------------------------------------------------------

_LOOK_X_RE = re.compile(
    r"^(?P<may>you may )?look at the top x cards of your library, where x is (?P<expr>.+)$",
    re.IGNORECASE,
)
_TOP_ONE_RE = re.compile(
    r"^if you do, put one of those cards on top of your library and the rest on the "
    r"bottom of your library in any order$",
    re.IGNORECASE,
)
_EXILE_AMONG_RE = re.compile(
    r"^you may exile an? (?P<quality>[a-z ]+?) card with mana value x or less from among them$",
    re.IGNORECASE,
)
_REVEAL_UNSHARED_RE = re.compile(
    r"^you may reveal a creature card that doesn't share a creature type with a creature "
    r"you control from among those cards and put it into your hand$",
    re.IGNORECASE,
)
_REST_RANDOM_RE = re.compile(
    r"^put the rest on the bottom of your library in a random order$", re.IGNORECASE
)
_CAST_EXILED_RE = re.compile(
    r"^you may cast the exiled card without paying its mana cost$", re.IGNORECASE
)


def _shares_a_creature_type(game: "Game", card: CardState, player: Player) -> bool:
    """Whether `card` has a creature type (or is a changeling, CR 702.73a)
    that a creature `player` controls has (CR 205.3m)."""
    from ..models.card import Type

    mine = {subtype.lower() for subtype in card.subtypes}
    changeling = "changeling" in {str(k).lower() for k in card.card.keywords}
    for permanent in game.permanents_controlled_by(player.username):
        characteristics = game.characteristics_of(permanent)
        if Type.CREATURE not in characteristics.types:
            continue
        theirs = {subtype.lower() for subtype in characteristics.subtypes}
        their_changeling = "changeling" in {str(k).lower() for k in permanent.card.keywords}
        if (mine & theirs) or (changeling and theirs) or (their_changeling and mine):
            return True
    return False


def _choose_among(
    game: "Game",
    player: Player,
    options: list[CardState],
    prompt: str,
    *,
    required: bool,
    name: str | None,
    source_id: str | None,
) -> CardState | None:
    from .decisions import Decision, DecisionKind

    if not options:
        return None
    ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=prompt,
            source=name,
            source_id=source_id,
            amount=1,
            exact=required,
            cards=tuple(card.id for card in options),
        )
    )
    by_id = {card.id: card for card in options}
    return next((by_id[card_id] for card_id in ids if card_id in by_id), None)


def _step_look_top_x(
    phrase: Phrase,
    *,
    may: bool,
    kind: str,
    quality: str,
    cast_exiled: bool,
) -> ResolutionStep:
    """ "Look at the top X cards of your library" (CR 701.20e) and the pick the
    sentences after it make: `kind` "top" puts one on top and the rest on the
    bottom in any order (Cream of the Crop); "exile" exiles an `quality` card
    with mana value X or less, bottoms the rest in a random order and may cast
    the exiled card (Keldon Flamesage); "reveal" takes a creature card sharing no
    creature type with the creatures you control (Radagast the Brown)."""
    from .effects._common import _quality_matcher
    from .effects.library import _bottom_in_random_order

    matches = _quality_matcher(quality) if kind == "exile" else None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        player = game.controller_of(stack_object)
        name, source_id = _name_and_id(stack_object)
        amount = stat_value(game, stack_object, state, phrase)  # CR 608.2h: once
        if may and not game.may(
            player, "look at the top cards of your library", source=name, source_id=source_id
        ):
            return False
        looked = list(player.library[: max(amount, 0)])
        for card in looked:
            game.look(card, player.username, source=name)
        if kind == "top":
            chosen = _choose_among(
                game,
                player,
                looked,
                "choose one to keep on top of your library",
                required=True,
                name=name,
                source_id=source_id,
            )
            rest = [card for card in looked if card is not chosen]
            _bottom(game, player, rest, name=name, source_id=source_id)
            return True
        if kind == "exile":
            assert matches is not None
            options = [c for c in looked if matches(c) and int(c.mana_value) <= amount]
            chosen = _choose_among(
                game,
                player,
                options,
                f"exile {quality} card with mana value {amount} or less",
                required=False,
                name=name,
                source_id=source_id,
            )
            if chosen is not None:
                game.exile_permanent(chosen)
                state.card = chosen
                state.referent = card_snapshot(game, chosen)
            _bottom_in_random_order(
                game, player, [c for c in looked if c is not chosen and c.zone is Zone.LIBRARY]
            )
            if cast_exiled and chosen is not None and chosen.zone is Zone.EXILE:
                _step_cast_free(game, stack_object, state)
            return True
        options = [
            c for c in looked if c.card.is_creature and not _shares_a_creature_type(game, c, player)
        ]
        chosen = _choose_among(
            game,
            player,
            options,
            "reveal a creature card and put it into your hand",
            required=False,
            name=name,
            source_id=source_id,
        )
        if chosen is not None:
            game.reveal(chosen, source=name)
            player.add(chosen, Zone.HAND)
        _bottom_in_random_order(
            game, player, [c for c in looked if c is not chosen and c.zone is Zone.LIBRARY]
        )
        return True

    return step


def _look_macro(queue: list[str], position: int) -> tuple[ResolutionStep, int] | None:
    """The look sentence at `queue[position]` and the sentences after it that
    belong to it, as one step and the next position, or `None`."""
    if (look := _LOOK_X_RE.fullmatch(queue[position])) is None:
        return None
    phrase = parse_ref(look.group("expr"))
    if phrase is None:
        return None
    following = queue[position + 1 :]
    kind, quality, cast, used = "", "", False, 0
    if following and _TOP_ONE_RE.fullmatch(following[0]):
        kind, used = "top", 1
    elif following and (exile := _EXILE_AMONG_RE.fullmatch(following[0])):
        kind, quality, used = "exile", exile.group("quality"), 1
        if len(following) > used and _REST_RANDOM_RE.fullmatch(following[used]):
            used += 1
            if len(following) > used and _CAST_EXILED_RE.fullmatch(following[used]):
                cast, used = True, used + 1
        else:
            return None
    elif following and _REVEAL_UNSHARED_RE.fullmatch(following[0]):
        kind, used = "reveal", 1
        if len(following) > used and _REST_RANDOM_RE.fullmatch(following[used]):
            used += 1
        else:
            return None
    else:
        return None
    step = _step_look_top_x(
        phrase, may=bool(look.group("may")), kind=kind, quality=quality, cast_exiled=cast
    )
    return step, position + 1 + used


# --------------------------------------------------------------------------
# The whole text
# --------------------------------------------------------------------------

_IF_CANT_RE = re.compile(r"^if you can't (?P<what>.+?), (?P<rest>.+)$", re.IGNORECASE)
_IF_WIN_RE = re.compile(r"^if you win,? (?P<rest>.+)$", re.IGNORECASE)
_UNREAD_CONDITION_RE = re.compile(r"^(?:if|when|whenever|unless|as long as) ", re.IGNORECASE)
_IF_DONT_RE = re.compile(
    r"^if you don't(?: put it onto the battlefield)?,? (?P<rest>.+)$", re.IGNORECASE
)
_IF_CONTROL_RE = re.compile(
    r"^(?:then )?if (?P<cond>you control [^,]+), (?P<rest>.+)$", re.IGNORECASE
)
_IF_KIND_RE = re.compile(
    r"^if it's an? (?P<kinds>[a-z]+(?: or [a-z]+)*) card,? (?P<rest>.+)$", re.IGNORECASE
)
_MAY_RE = re.compile(r"^you may (?P<rest>.+)$", re.IGNORECASE)
_COMPOUND_AND_RE = re.compile(
    r"^(?P<first>tap this creature) and (?P<second>you .+)$", re.IGNORECASE
)
_PUT_IT_IN_HAND_RE = re.compile(r"^put it into your hand$", re.IGNORECASE)
_LEADING_LIFE_RE = re.compile(r", (?=(?:lose|gain) life )")

_GATE_WORDS = (
    "power",
    "toughness",
    "mana value",
    "the exiled card",
    "highest life total",
    "controller sacrifices it",
    "a copy of that card",
    "a copy of it",
)
_GATE_FORMS = (
    "equal to",
    "where x is",
    "deals x damage",
    "the exiled card",
    "controller sacrifices it",
    ", except ",
)


def _expand(sentence: str) -> list[str]:
    """One compound sentence as the clauses it is: "you gain life equal to A,
    lose life equal to B, then put it into your hand" (Sapling of Colfenor), "tap
    this creature and you lose 7 life". An "if ..." lead-in applies to each."""
    lead = ""
    for guard in (_IF_KIND_RE, _IF_CANT_RE, _IF_WIN_RE, _IF_YOU_DO_RE):
        if (match := guard.fullmatch(sentence)) is not None:
            lead = sentence[: sentence.index(match.group("rest"))]
            sentence = match.group("rest")
            break
    pieces: list[str] = []
    for part in re.split(r", then (?!put up to x land)", sentence, flags=re.IGNORECASE):
        pieces.extend(_LEADING_LIFE_RE.split(part))
    expanded: list[str] = []
    for piece in pieces:
        if (match := _COMPOUND_AND_RE.fullmatch(piece)) is not None:
            expanded.extend((match.group("first"), match.group("second")))
        else:
            expanded.append(piece)
    if len(expanded) == 1 and not lead:
        return [sentence]
    return [f"{lead}{piece}" for piece in expanded]


def _compile(sentences: list[str], *, for_spell: bool) -> list[ResolutionStep] | None:
    steps: list[ResolutionStep] = []
    queue = [piece for sentence in sentences for piece in _expand(sentence)]
    position = 0
    opened = False
    uses_amount = False
    # A text that is one plain sentence is what the established readers are
    # reading right now: asking them for it again is a re-entrant parse, which
    # answers `None` and caches it for the outer call.
    allow_plain = not (len(sentences) == 1 and len(queue) == 1)
    if "the exiled card" in " ".join(queue).lower() and not any(
        _EXILE_PERMANENT_FROM_GRAVEYARD_RE.fullmatch(sentence) for sentence in queue
    ):
        steps.append(_step_load_exiled_card)  # an earlier ability exiled it (CR 607.2a)
        opened = True
    while position < len(queue):
        if (look := _look_macro(queue, position)) is not None:
            steps.append(look[0])
            position = look[1]
            uses_amount = True
            continue
        sentence = queue[position]
        position += 1
        guard: Callable[[RunState], bool] | None = None
        condition: str | None = None
        sentence = re.sub(r"^then ", "", sentence, flags=re.IGNORECASE)
        if match := _IF_CONTROL_RE.fullmatch(sentence):
            sentence, condition = match.group("rest"), match.group("cond")
        elif match := _IF_DONT_RE.fullmatch(sentence):
            sentence, guard = match.group("rest"), lambda s: not s.did
        elif match := _IF_YOU_DO_RE.fullmatch(sentence):
            sentence, guard = match.group("rest"), lambda s: s.did
        elif match := _IF_CANT_RE.fullmatch(sentence):
            sentence, guard = match.group("rest"), lambda s: not s.did
        elif match := _IF_WIN_RE.fullmatch(sentence):
            sentence, guard = match.group("rest"), lambda s: s.did
        elif match := _IF_KIND_RE.fullmatch(sentence):
            kinds = [kind.lower() for kind in match.group("kinds").split(" or ")]
            sentence = match.group("rest")
            guard = lambda s, kinds=kinds: (  # noqa: E731
                s.referent is not None and any(s.referent.is_a(kind) for kind in kinds)
            )
        if _UNREAD_CONDITION_RE.match(sentence) and not _ON_BATTLEFIELD_RE.match(sentence):
            return None  # a condition none of the guards above reads: never run it unconditionally
        if re.match(r"^(?:gain|lose) ", sentence, re.IGNORECASE):
            sentence = f"you {sentence}"
        step: ResolutionStep | None = None
        opener = _extra_opener(sentence, for_spell=for_spell)
        if opener is None and (first := _opener(sentence, for_spell=for_spell)) is not None:
            opener = (
                (first[0], first[1])
                if first[1] is None
                else (
                    first[0],
                    _unwrap_then(sentence, first[1], first[2])[0],
                )
            )
        if opener is not None:
            step, tail = opener
            opened = True
            uses_amount = uses_amount or _spends_amount(sentence)
            if tail:
                queue.insert(position, tail)
        else:
            step = _extra_step(sentence, for_spell=for_spell)
            if step is None and (may := _MAY_RE.fullmatch(sentence)) is not None:
                inner = _extra_step(may.group("rest"), for_spell=for_spell)
                step = None if inner is None else _asked(inner)
            if step is None:
                step = _amount_step(sentence, for_spell=for_spell, opener=opened)
            if step is None and allow_plain:
                step = _step_plain(sentence, for_spell=for_spell)
            if step is None:
                return None
            uses_amount = uses_amount or _spends_amount(sentence)
        if condition is not None:
            step = _conditioned(step, condition)
        steps.append(_gated(step, guard) if guard is not None else step)
    if not uses_amount:
        return None
    return steps


def _spends_amount(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(word in lowered for word in _GATE_WORDS) or "where x is" in lowered


def _asked(step: ResolutionStep) -> ResolutionStep:
    def asked(game: "Game", stack_object: Any, state: State) -> bool:
        name, source_id = _name_and_id(stack_object)
        if not game.may(
            game.controller_of(stack_object), "do it", source=name, source_id=source_id
        ):
            return True
        return step(game, stack_object, state)

    return asked


def _gated(step: ResolutionStep, test: Callable[[RunState], bool]) -> ResolutionStep:
    def gated(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        return step(game, stack_object, state) if test(state) else True

    return gated


@functools.cache
def referenced_permanent_stat_effect(
    text: str, *, for_spell: bool
) -> Callable[["Game", Any], None] | None:
    """The effect of `text` when it spends a characteristic of a permanent or
    card an earlier part of the text, its cost or its trigger named, or `None`
    for anything else."""
    lowered = text.lower()
    if not any(word in lowered for word in _GATE_WORDS):
        return None
    if not any(form in lowered for form in _GATE_FORMS):
        return None
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble

    sentences = [
        _clean(sentence)
        for sentence in _plain_resolution_sentences(
            _strip_non_effect_preamble(" ".join(text.split()))
        )
    ]
    sentences = [s for s in sentences if s]
    if not sentences:
        return None
    steps = _compile(sentences, for_spell=for_spell)
    if steps is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        state = Run()
        for step in steps:
            if not step(game, stack_object, state):
                return

    return effect


# --------------------------------------------------------------------------
# Epic (CR 702.50)
# --------------------------------------------------------------------------

_EPIC_RE = re.compile(r"^(?P<body>.+?)\s*\n\s*epic(?: \(.*\))?\s*$", re.IGNORECASE | re.DOTALL)


def _begin_epic(game: "Game", spell: CardState) -> None:
    """CR 702.50a, the two spell abilities an epic spell's resolution runs: the
    controller can't cast spells for the rest of the game (CR 702.50b: copies
    are not cast, so the copies below are unaffected), and at the beginning of
    each of their upkeeps the spell is copied."""
    from .abilities import TriggerEvent
    from .casting_restrictions import CastingRuleEffect, CastingRuleKind
    from .delayed import DelayedTrigger, EpicCopy
    from .layers import Duration
    from .turn import Step

    you = game.controller_of(spell).username
    game.casting_rule_effects.append(
        CastingRuleEffect(
            kind=CastingRuleKind.TARGETED_CANT_CAST,
            controller=you,
            source_name=spell.name,
            duration=Duration.INDEFINITE,
            restricted_player=you,
        )
    )
    game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of each of your upkeeps, copy this spell except for its epic.",
            effect=EpicCopy(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.UPKEEP,
            controller=you,
            source_id=spell.id,
            source_name=spell.name,
            only_when_active=you,
            remaining=None,
        )
    )


@functools.cache
def epic_spell_effect(text: str) -> Callable[["Game", Any], None] | None:
    """A spell whose text ends in an epic line: what the rest of the text does,
    then the epic abilities (CR 702.50a) - none for a copy, which is "except for
    its epic ability"."""
    if "\nepic" not in text.lower() or (match := _EPIC_RE.fullmatch(text.strip())) is None:
        return None
    from .effects.dispatch import _spell_effect_or_notice

    body = _spell_effect_or_notice(match.group("body"))
    if body is None:
        return None

    def effect(game: "Game", spell: Any) -> None:
        body(game, spell)
        if isinstance(spell, CardState) and not spell.is_copy:
            _begin_epic(game, spell)

    return effect
