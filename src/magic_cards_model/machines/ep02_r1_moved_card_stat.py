"""EP-02 R1 T7: the power, toughness, mana value or counters of a card or spell
that the same text just moved, used as an amount.

"Create X tokens, where X is the sacrificed creature's toughness", "Lie in
Wait deals damage equal to that card's power" (the card it returned),
"create X 1/1 Saprolings, where X is the exiled card's toughness", "draw
cards equal to that spell's mana value" (the spell it countered), "you gain
life equal to the number of counters on it" (the permanent it exiled).

`ep02_r1_referenced_stat` (T6) reads a creature an earlier sentence named; this
module extends it to the objects that module does not follow:

- a card a graveyard gave up (returned to hand, put on top of the library,
  exiled), read as the card it is there (its printed characteristics, CR
  400.7), not as the permanent it once was;
- a spell countered (CR 701.6a), read off the stack before it leaves it;
- a creature sacrificed by the text itself ("you may sacrifice another
  creature. If you do, ..."; "its controller sacrifices it, then ...") rather
  than by a cost, so the token or the damage is sized by what the sacrifice
  moved (CR 701.21a, last known information CR 608.2h);
- a card exiled to pay a cost ("Exile a creature card from your graveyard:
  ..."), read from what the cost recorded (CR 602.2b);
- the amounts themselves: tokens sized or counted by the stat, a pump sized by
  it, counters on a creature, damage to a target / each opposing creature /
  the moved object's controller, life gained and lost, cards drawn.

A negative characteristic counts as zero (CR 107.1b). An amount that names an
object nothing moved counts as zero.
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any
from uuid import UUID

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone
from .amount_sentences import (
    TokenMaker,
    apply_life,
    apply_mill,
    parse_cards_clause,
    parse_create,
    parse_damage_clause,
    parse_life_clause,
    parse_mill_clause,
    parse_put_counters,
    split_where_x,
    token_maker,
)
from .ep01_r3_amounts import counters_on_it_total
from .ep02_r1_referenced_stat import (
    Anchor,
    Referent,
    default_referent,
    normalize,
    parse_stat_phrase,
    snapshot_of,
    stat_value,
)

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# The referenced object
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Moved(Referent):
    """A moved object's characteristics at the moment it moved (CR 608.2h),
    with the counters it carried and who controlled it."""

    counters: int = 0
    controller: str | None = None


def card_snapshot(game: "Game", card: CardState) -> Moved:
    """`card` as it is right now: a battlefield permanent from the computed
    board with its counters and controller (CR 613.5), anything else - a
    graveyard card, a spell on the stack - as the printed card it is
    (CR 400.7: it is a new object, with no memory of the permanent it was)."""
    if card.zone is Zone.BATTLEFIELD:
        base = snapshot_of(game, card)
        counters = counters_on_it_total(card)
        controller: str | None = game.controller_of(card).username
    else:
        characteristics = game.characteristics_of(card)
        base = Referent(
            card_id=card.id,
            power=characteristics.power,
            toughness=characteristics.toughness,
            mana_value=int(game.last_known_mana_value(card)),
            types=frozenset(str(kind.value).lower() for kind in characteristics.types),
            subtypes=frozenset(sub.lower() for sub in characteristics.subtypes),
        )
        counters = 0
        controller = None
        if card.zone is Zone.STACK:
            controller = game.controller_of(card).username
            record = game.cast_record_of(card)
            if record is not None:
                # CR 202.3e: on the stack an {X} in the cost is the value chosen for it.
                base = replace(
                    base,
                    mana_value=base.mana_value
                    + (card.mana_cost or "").count("{X}") * record.x_value,
                )
    return Moved(
        card_id=base.card_id,
        power=base.power,
        toughness=base.toughness,
        mana_value=base.mana_value,
        types=base.types,
        subtypes=base.subtypes,
        counters=counters,
        controller=controller,
    )


def moved_stat_value(referent: Referent | None, stat: str) -> int:
    """The characteristic `stat` names ("counters" included), never negative."""
    if stat == "counters":
        return max(getattr(referent, "counters", 0), 0)
    return stat_value(referent, stat)


# --------------------------------------------------------------------------
# The amount phrase
# --------------------------------------------------------------------------

_STATS = r"power|toughness|mana value"
_MOVED_SUBJECT = (
    r"(?:that|the exiled|the returned|the sacrificed)"
    r"(?: (?:creature|artifact|permanent|nonland|instant|sorcery))*"
    r" (?:card|creature|permanent|artifact|spell)"
    r"|the spell|that spell"
    r"|the (?:milled |revealed |discarded )?card"
)
_MOVED_POSSESSIVE_RE = re.compile(
    rf"^(?P<subject>{_MOVED_SUBJECT})'s (?P<stat>{_STATS})$|^its (?P<its_stat>{_STATS})$"
)
_MOVED_OF_RE = re.compile(
    rf"^the (?P<stat>{_STATS}) of (?P<subject>the card you exiled|the card returned this way"
    r"|the card exiled this way|the exiled (?:creature )?card|that (?:card|spell|creature)"
    r"|the sacrificed creature|it)$"
)
_COUNTERS_RE = re.compile(r"^the number of counters on (?:it|that (?:creature|permanent))$")


@dataclass(frozen=True)
class Phrase:
    anchor: str
    """"sacrificed" (a cost's or the text's sacrifice), "exiled" (a cost's
    exile), "anaphor" (what an earlier part of the text or the trigger event
    named)."""
    stat: str
    spell: bool = False
    """The phrase names a spell ("that spell's mana value")."""


@functools.cache
def parse_moved_phrase(phrase: str) -> Phrase | None:
    """ "that card's power", "the exiled card's toughness", "that spell's mana
    value", "the power of the card you exiled", "the number of counters on
    it" as a `Phrase`; T6's own phrases ("its toughness", "the sacrificed
    creature's power") are read by `parse_stat_phrase`."""
    text = normalize(phrase)
    if _COUNTERS_RE.fullmatch(text):
        return Phrase("anaphor", "counters")
    match = _MOVED_POSSESSIVE_RE.fullmatch(text)
    if match is not None and match.group("subject") is not None:
        subject = match.group("subject")
        anchor = (
            "sacrificed"
            if "sacrificed" in subject
            else "exiled"
            if "exiled" in subject
            else "discarded"
            if "discarded" in subject
            else "anaphor"
        )
        return Phrase(anchor, match.group("stat"), spell=subject.endswith("spell"))
    match = _MOVED_OF_RE.fullmatch(text)
    if match is not None:
        subject = match.group("subject")
        anchor = (
            "sacrificed"
            if "sacrificed" in subject
            else "exiled"
            if "exiled" in subject
            else "anaphor"
        )
        return Phrase(anchor, match.group("stat"), spell=subject.endswith("spell"))
    ref = parse_stat_phrase(text)
    if ref is None:
        return None
    return Phrase("sacrificed" if ref.anchor is Anchor.SACRIFICED else "anaphor", ref.stat)


# --------------------------------------------------------------------------
# What a cost paid
# --------------------------------------------------------------------------


def _cost_exiled_referent(game: "Game", stack_object: Any) -> Moved | None:
    """The card an activation's cost exiled (CR 602.2b), or a spell's
    additional cost did (CR 601.2b); it is in exile now, so it reports the
    printed card it was in the graveyard."""
    ids: tuple[UUID, ...] = tuple(getattr(stack_object, "cost_exiled_card_ids", ()) or ())
    single = getattr(stack_object, "cost_exiled_card_id", None)
    if not ids and single is not None:
        ids = (single,)
    if not ids and isinstance(stack_object, CardState):
        record = game.cast_record_of(stack_object)
        if record is not None:
            ids = tuple(record.additional_cost_cards)
    for card_id in ids:
        card = game.find_by_id(card_id)
        if card is not None:
            return card_snapshot(game, card)
    if getattr(stack_object, "source_id", None) is not None:
        # "The exiled card" of a later chapter or ability: the card the source's
        # own exiling ability linked to it (CR 607.2a).
        from .exiled_with_peek import _pile

        pile = _pile(game, stack_object)
        if pile:
            return card_snapshot(game, pile[-1])
    return None


def _cost_discarded_referent(game: "Game", stack_object: Any) -> Moved | None:
    """The card an activation's cost discarded (CR 602.2b), with the mana value
    it had when it was discarded (CR 608.2h)."""
    ids: tuple[UUID, ...] = tuple(getattr(stack_object, "cost_discarded_card_ids", ()) or ())
    values = tuple(getattr(stack_object, "cost_discarded_mana_values", ()) or ())
    for position, card_id in enumerate(ids):
        card = game.find_by_id(card_id)
        if card is not None:
            snapshot = card_snapshot(game, card)
            if position < len(values):
                snapshot = replace(snapshot, mana_value=int(values[position]))
            return snapshot
    return None


def _referent_for(game: "Game", stack_object: Any, state: "State", anchor: str) -> Referent | None:
    """The object an amount phrase refers to: what the text itself moved
    first, then what the cost paid, then the trigger event's subject."""
    if state.referent is not None:
        return state.referent
    if anchor == "exiled":
        return _cost_exiled_referent(game, stack_object)
    if anchor == "discarded":
        return _cost_discarded_referent(game, stack_object)
    return default_referent(
        game, stack_object, Anchor.SACRIFICED if anchor == "sacrificed" else Anchor.ANAPHOR
    )


# --------------------------------------------------------------------------
# The run state and the steps
# --------------------------------------------------------------------------


@dataclass
class State:
    """What one resolution has established so far."""

    referent: Moved | None = None
    did: bool = False
    legal: list[Any] | None = None
    cursor: int = 0
    token_controller: str | None = None
    player: str | None = None
    """"that player": whose card the text just revealed or discarded."""

    def targets(self, game: "Game", stack_object: Any) -> list[Any]:
        if self.legal is None:
            self.legal = [game.legal_target(stack_object, ref) for ref in stack_object.targets]
        return self.legal

    def first_target(self, game: "Game", stack_object: Any) -> Any:
        """The first target, for "that permanent or player" / "that creature"
        looking back at what the text chose, without consuming it."""
        legal = self.targets(game, stack_object)
        return legal[0] if legal else None

    def next_target(self, game: "Game", stack_object: Any) -> Any:
        """The next target in printed order, `None` if it is illegal now or
        none was chosen ("up to one target")."""
        legal = self.targets(game, stack_object)
        if self.cursor >= len(legal):
            return None
        target = legal[self.cursor]
        self.cursor += 1
        return target


ResolutionStep = Callable[["Game", Any, State], bool]
"""One part of the text. Returns `False` to end the resolution (a declined
"you may", a missing target)."""


def _opponents(game: "Game", controller: str) -> list[str]:
    return [player.username for player in game.players if player.username != controller]


def _source_card(game: "Game", stack_object: Any) -> CardState | None:
    if isinstance(stack_object, CardState):
        return stack_object
    return stack_object.source_or_last_known(game)


# ---- openers: they move something and fix what later sentences refer to ----

_RETURN_RE = re.compile(
    r"^return target (?:(?P<quality>.+?) )?card from your graveyard to your hand$", re.IGNORECASE
)
_PUT_ON_TOP_RE = re.compile(
    r"^you may put target (?P<quality>.+?) card from your graveyard on top of your library$",
    re.IGNORECASE,
)
_EXILE_GRAVEYARD_RE = re.compile(
    r"^exile target (?:(?P<quality>.+?) )?card from (?:your|a|an opponent's) graveyard"
    r"(?: that was put there from the battlefield this turn)?"
    r"(?:,? then (?P<rest>.+))?$",
    re.IGNORECASE,
)
_COUNTER_RE = re.compile(r"^counter target (?:(?P<quality>[a-z]+) )?spell$", re.IGNORECASE)
_EXILE_TARGET_RE = re.compile(
    r"^exile target (?P<what>(?:creature|permanent|artifact)[^,.]*)$", re.IGNORECASE
)
_SACRIFICE_RE = re.compile(
    r"^(?P<may>you may )?sacrifice (?P<restriction>(?:another|a|an) [a-z ]+)$", re.IGNORECASE
)
_CONTROLLER_SACRIFICES_RE = re.compile(
    r"^target creature's controller sacrifices it(?:,? then (?P<rest>.+))?$", re.IGNORECASE
)
_EXILE_TOP_RE = re.compile(r"^exile the top card of your library$", re.IGNORECASE)


def _graveyard_card(state: State, game: "Game", stack_object: Any) -> CardState | None:
    target = state.next_target(game, stack_object)
    return target if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD else None


def _step_return_to_hand(game: "Game", stack_object: Any, state: State) -> bool:
    card = _graveyard_card(state, game, stack_object)
    if card is None:
        return True
    state.referent = card_snapshot(game, card)
    game.return_to_hand(card)
    state.did = card.zone is Zone.HAND
    return True


def _step_put_on_top(game: "Game", stack_object: Any, state: State) -> bool:
    from .decisions import source_id_of

    card = _graveyard_card(state, game, stack_object)
    if card is None:
        return False
    if not game.may(
        game.controller_of(stack_object),
        "put the card on top of your library",
        source=getattr(stack_object, "source_name", None) or getattr(stack_object, "name", None),
        source_id=source_id_of(stack_object),
    ):
        return False
    state.referent = card_snapshot(game, card)
    game.put_cards_into_library([card])
    state.did = card.zone is Zone.LIBRARY
    return True


def _step_exile_from_graveyard(game: "Game", stack_object: Any, state: State) -> bool:
    card = _graveyard_card(state, game, stack_object)
    if card is None:
        return True
    state.referent = card_snapshot(game, card)
    game.exile_cards([card])
    state.did = card.zone is Zone.EXILE
    return True


def _step_counter_spell(game: "Game", stack_object: Any, state: State) -> bool:
    spell = state.next_target(game, stack_object)
    if not isinstance(spell, CardState):
        return True
    state.referent = card_snapshot(game, spell)
    game.counter(spell)
    state.did = True
    return True


def _step_delegate_to_target(opening: str, *, for_spell: bool) -> ResolutionStep | None:
    """ "Exile target creature or planeswalker.": the established reader does
    the move, this step fixes the target's characteristics and counters first
    (CR 608.2h)."""
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell

    first = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(opening)
    if first is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        target = state.next_target(game, stack_object)
        if not isinstance(target, CardState):
            return True
        state.referent = card_snapshot(game, target)
        first(game, stack_object)
        state.did = target.zone is not Zone.BATTLEFIELD
        return True

    return step


def _step_controller_sacrifices(game: "Game", stack_object: Any, state: State) -> bool:
    target = state.next_target(game, stack_object)
    if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return True
    state.referent = card_snapshot(game, target)
    state.token_controller = state.referent.controller
    game.sacrifice(target)
    state.did = target.zone is not Zone.BATTLEFIELD
    return True


def _step_exile_top(game: "Game", stack_object: Any, state: State) -> bool:
    player = game.controller_of(stack_object)
    if not player.library:
        return False
    top = player.library[0]
    state.referent = card_snapshot(game, top)
    game.exile_permanent(top)
    state.did = top.zone is Zone.EXILE
    return True


def _step_sacrifice(restriction_text: str, *, may: bool, for_spell: bool) -> ResolutionStep | None:
    from .decisions import Decision, DecisionKind, source_id_of
    from .effects._common import _permanent_id_and_name
    from .effects.modal import _choose_permanents_to_sacrifice
    from .effects.removal import _sacrifice_is_payable, _sacrifice_restriction

    restriction = _sacrifice_restriction(restriction_text)
    if restriction is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = restriction.candidates(game, player, source_id)
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
            return False
        chosen = _choose_permanents_to_sacrifice(
            game,
            player,
            restriction,
            candidates,
            source_name=source_name,
            source_id=source_id_of(stack_object),
        )
        if len(chosen) != 1:
            return False
        state.referent = card_snapshot(game, chosen[0])
        game.sacrifice(chosen[0])
        state.did = chosen[0].zone is not Zone.BATTLEFIELD
        return True

    return step


# ---- the sentences that spend an amount ----

_IF_YOU_DO_RE = re.compile(r"^(?:if you do|when you do),? (?P<rest>.+)$", re.IGNORECASE)
_IF_RETURNED_RE = re.compile(
    r"^if you return an? (?P<quality>[a-z]+) card to your hand this way,? (?P<rest>.+)$",
    re.IGNORECASE,
)
_IF_IT_IS_RE = re.compile(r"^if it's an? (?P<kind>[a-z]+) card,? (?P<rest>.+)$", re.IGNORECASE)

_DOUBLED_RE = re.compile(
    r"^if the sacrificed creature was an? (?P<kind>[a-z]+),? .+? deals twice that much "
    r"damage instead$",
    re.IGNORECASE,
)
_TOKEN_STATS_RE = re.compile(
    r"^create an? (?P<desc>.+?) \btoken\b$",
    re.IGNORECASE,
)
_TOKEN_SIZE_RE = re.compile(
    r"^its power is equal to (?P<power>.+?) and its toughness is equal to (?P<toughness>.+)$",
    re.IGNORECASE,
)
_PUMP_RE = re.compile(
    r"^(?:until end of turn, )?"
    r"(?P<subject>target creature(?: you control)?|that creature|this creature|this permanent|"
    r"(?-i:[A-Z][^ ]*(?: [A-Z][^ ]*)*)) "
    r"(?:gains (?P<grants>[a-z]+(?:, [a-z]+)*) and )?"
    r"gets (?P<power>[+-](?:x|\d+))/(?P<toughness>[+-](?:x|y|\d+))(?: until end of turn)?$",
    re.IGNORECASE,
)
_X_AND_Y_RE = re.compile(r"^(?P<xstat>.+?)(?: and y is (?P<ystat>.+))?$", re.IGNORECASE)
_COUNTERS_ON_RE = re.compile(r"^(?:it|target creature(?: you control)?)$", re.IGNORECASE)


def _phrase(text: str) -> Phrase | None:
    return parse_moved_phrase(text)


def _amount(game: "Game", stack_object: Any, state: State, phrase: Phrase) -> int:
    return moved_stat_value(_referent_for(game, stack_object, state, phrase.anchor), phrase.stat)


def _step_x_pair(parts: tuple[tuple[str, str, bool], ...], phrase: Phrase) -> ResolutionStep:
    """ "You gain X life and draw X cards", "target player loses X life and you
    gain X life", where X is the stat: the parts in order (CR 608.2c), one
    amount for both (CR 608.2h)."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = _amount(game, stack_object, state, phrase)
        for verb, who, gains in parts:
            if verb == "draw":
                game.draw_cards(game.controller_of(stack_object), amount)
            else:
                apply_life(game, stack_object, who, gains, lambda *_: amount)
        return True

    return step


#: The players a life clause may name; "that player" is the one the text just
#: revealed a card of.
_LIFE_WHO = (
    "you",
    "target player",
    "target opponent",
    "each opponent",
    "each player",
    "that player",
)


def _x_pair(body: str) -> tuple[tuple[str, str, bool], ...] | None:
    """The two parts of an "X life and X life/cards" body, the second
    inheriting the first's subject when it prints none."""
    parts: list[tuple[str, str, bool]] = []
    subject = ""
    for part in re.split(r"\s+and\s+", body):
        life = parse_life_clause(part)
        if life is not None and life.kind == "x" and life.expr is None and life.n == 1:
            subject = life.who or subject
            if subject not in _LIFE_WHO:
                return None
            parts.append(("life", subject, life.gains))
            continue
        cards = parse_cards_clause(part)
        if cards is not None and cards.draws and cards.kind == "x":
            if (cards.who or subject) != "you":
                return None
            parts.append(("draw", "you", False))
            continue
        return None
    return tuple(parts) if len(parts) == 2 else None


def _step_life_equal(who: str, gains: bool, phrase: Phrase) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = _amount(game, stack_object, state, phrase)
        targets = [state.next_target(game, stack_object)] if who.startswith("target") else None
        fallback = () if state.player is None else (state.player,)
        apply_life(
            game, stack_object, who, gains, lambda *_: amount, targets=targets, fallback=fallback
        )
        return True

    return step


_MILL_WHO = ("", "you", "target player", "target opponent", "each opponent", "that player")


def _step_mill(who: str, phrase: Phrase) -> ResolutionStep:
    """ "<Player> mills X cards, where X is the stat": a player the text names,
    or the controller of the object the amount names."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = _amount(game, stack_object, state, phrase)
        if _ITS_CONTROLLER_RE.fullmatch(who):
            referent = _referent_for(game, stack_object, state, phrase.anchor)
            owner = getattr(referent, "controller", None)
            if owner is not None:
                apply_mill(game, stack_object, "that player", lambda *_: amount, fallback=(owner,))
            return True
        targets = [state.next_target(game, stack_object)] if who.startswith("target") else None
        fallback = () if state.player is None else (state.player,)
        apply_mill(
            game, stack_object, who or "you", lambda *_: amount, targets=targets, fallback=fallback
        )
        return True

    return step


def _step_draw(phrase: Phrase) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        game.draw_cards(
            game.controller_of(stack_object), _amount(game, stack_object, state, phrase)
        )
        return True

    return step


_EACH_RE = re.compile(
    r"^each (?P<kinds>(?:creature|planeswalker)(?: and each (?:creature|planeswalker))*)"
    r"(?: (?P<who>your opponents|an opponent|you don't) controls?)?$",
    re.IGNORECASE,
)
_ITS_CONTROLLER_RE = re.compile(
    r"^(?:its|that (?:spell|creature|permanent)'s) controller$", re.IGNORECASE
)
_TARGET_RE = re.compile(r"^(?:up to one )?(?:another )?target .+$|^any target$", re.IGNORECASE)
_THAT_RE = re.compile(
    r"^that (?P<what>permanent or player|player|creature|permanent|planeswalker)$", re.IGNORECASE
)


@dataclass
class _Damage:
    """ "<Source> deals damage equal to <stat> to <recipient>."; `doubled_for`
    is the kind named by a following "If the sacrificed creature was a <kind>,
    ... deals twice that much damage instead.\""""

    phrase: Phrase
    recipient: str
    doubled_for: str | None = None

    def __call__(self, game: "Game", stack_object: Any, state: State) -> bool:
        referent = _referent_for(game, stack_object, state, self.phrase.anchor)
        amount = moved_stat_value(referent, self.phrase.stat)
        if (
            self.doubled_for is not None
            and referent is not None
            and referent.is_a(self.doubled_for)
        ):
            amount *= 2
        source = _source_card(game, stack_object)
        recipient = self.recipient
        if (each := _EACH_RE.fullmatch(recipient)) is not None:
            kinds = {word.lower() for word in re.findall(r"creature|planeswalker", each["kinds"])}
            controller = game.controller_of(stack_object).username
            if each["who"] is None:
                holders = [player.username for player in game.players]
            else:
                holders = _opponents(game, controller)
            for holder in holders:
                for permanent in list(game.permanents_controlled_by(holder)):
                    types = {str(k.value).lower() for k in game.characteristics_of(permanent).types}
                    if types & kinds:
                        game.deal_damage(permanent, amount, source=source)
        elif _ITS_CONTROLLER_RE.fullmatch(recipient):
            owner = None if referent is None else getattr(referent, "controller", None)
            if owner is not None:
                game.deal_damage(game.player(owner), amount, source=source)
        elif (that := _THAT_RE.fullmatch(recipient)) is not None:
            if that["what"].lower() == "player" and state.player is not None:
                target = game.player(state.player)
            else:
                target = state.first_target(game, stack_object)
            if target is not None:
                game.deal_damage(target, amount, source=source)
        else:
            target = state.next_target(game, stack_object)
            if target is not None:
                game.deal_damage(target, amount, source=source)
        return True


def _step_made_tokens(make: TokenMaker, phrase: Phrase, *, who: str = "") -> ResolutionStep:
    """X tokens, or one X/X, where X is the stat (`amount_sentences.token_maker`).
    "That player creates" is the controller of the object the amount names
    (CR 111.2: the creator owns the token)."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        controller = state.token_controller or game.controller_of(stack_object).username
        if who == "that player":
            referent = _referent_for(game, stack_object, state, phrase.anchor)
            controller = getattr(referent, "controller", None) or state.player or controller
        make(game, controller, _amount(game, stack_object, state, phrase))
        return True

    return step


def _step_stat_sized_token(desc: str, size_stats: tuple[Phrase, Phrase]) -> ResolutionStep | None:
    """One token whose power and toughness are two stats ("Create a ...
    token. Its power is equal to ... and its toughness is equal to ...")."""
    from ..models.token import create_tokens
    from .effects.tokens import _token_definition_from_words

    @functools.cache
    def build(power: int, toughness: int) -> Any:
        return _token_definition_from_words(f"{power}/{toughness} {desc.strip()}", None)

    # Parse once with a sample so an unreadable descriptor fails the whole text.
    if build(1, 1) is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        controller = state.token_controller or game.controller_of(stack_object).username
        power = _amount(game, stack_object, state, size_stats[0])
        toughness = _amount(game, stack_object, state, size_stats[1])
        create_tokens(game, build(power, toughness), controller, 1)
        return True

    return step


def _step_pump(
    subject: str,
    power: str,
    toughness: str,
    x_phrase: Phrase,
    y_phrase: Phrase | None,
    grants: str = "",
) -> ResolutionStep | None:
    """ "<Target creature | This creature> gets +X/+Y until end of turn, where X
    is ...": the pump with the numbers written in, made by the layer system
    the way every other "until end of turn" pump is (CR 611.2)."""
    from .effects.continuous import continuous_effects, layer_context_for

    on_target = subject.lower().startswith("target creature")
    on_that = subject.lower() == "that creature"

    def literal(x: int, y: int) -> str:
        def number(spec: str) -> str:
            word = spec[1:].lower()
            value = x if word == "x" else y if word == "y" else int(word)
            return f"{spec[0]}{value}"

        who = "Target creature" if on_target or on_that else "This creature"
        gains = f" gains {grants} and" if grants else ""
        return f"{who}{gains} gets {number(power)}/{number(toughness)} until end of turn."

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        x = _amount(game, stack_object, state, x_phrase)
        y = 0 if y_phrase is None else _amount(game, stack_object, state, y_phrase)
        source = _source_card(game, stack_object)
        if on_that:
            recipient = state.first_target(game, stack_object)
        else:
            recipient = state.next_target(game, stack_object) if on_target else source
        if (
            source is None
            or not isinstance(recipient, CardState)
            or recipient.zone is not Zone.BATTLEFIELD
        ):
            return True
        continuous_effects(game).create(
            source,
            targets=[recipient],
            context=layer_context_for(game, game.controller_of(stack_object)),
            ability_text=literal(x, y),
            game=game,
        )
        return True

    return step


def _step_counters(kind: str, on: str, phrase: Phrase) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        amount = _amount(game, stack_object, state, phrase)
        if on.lower() == "it":
            event = getattr(stack_object, "event", None)
            subject_id = getattr(event, "subject_id", None)
            recipient = None if subject_id is None else game.find_by_id(subject_id)
        else:
            recipient = state.next_target(game, stack_object)
        if amount > 0 and isinstance(recipient, CardState) and recipient.zone is Zone.BATTLEFIELD:
            game.add_counters(recipient, kind, amount)
        return True

    return step


def _guarded(step: ResolutionStep, test: Callable[[State], bool]) -> ResolutionStep:
    def guarded(game: "Game", stack_object: Any, state: State) -> bool:
        if not test(state):
            return True
        return step(game, stack_object, state)

    return guarded


# --------------------------------------------------------------------------
# The whole text
# --------------------------------------------------------------------------


def _clean(sentence: str) -> str:
    return collapsed(sentence.replace("’", "'")).rstrip(".").strip()


def _amount_step(sentence: str, *, for_spell: bool, opener: bool) -> ResolutionStep | None:
    """One sentence that spends an amount.

    With no opener in the text, an amount that refers to "its" / "that
    creature's" / "that spell's" is the trigger event's or the target's, which
    the established readers own (damage "equal to its power", "put X counters
    ... where X is that spell's mana value"); only the shapes none of them
    read are taken here: a target pumped by its own power, counters on a
    target or on the entering creature, and life and cards from a creature
    that died."""

    def barred(phrase: Phrase, *, allowed: bool) -> bool:
        return not opener and phrase.anchor == "anaphor" and (not allowed or phrase.spell)

    where = split_where_x(sentence)
    body, tail = where if where is not None else (sentence, "")
    if where is not None and (pair := _x_pair(body)) and (p := _phrase(tail)):
        return None if barred(p, allowed=True) else _step_x_pair(pair, p)
    life = parse_life_clause(sentence)
    if (
        life is not None
        and life.kind == "equal"
        and life.who in _LIFE_WHO
        and (p := _phrase(life.expr or ""))
    ):
        return None if barred(p, allowed=False) else _step_life_equal(life.who, life.gains, p)
    cards = parse_cards_clause(sentence)
    if (
        cards is not None
        and cards.draws
        and cards.kind == "equal"
        and cards.who in ("", "you")
        and (p := _phrase(cards.expr or ""))
    ):
        return None if barred(p, allowed=False) else _step_draw(p)
    damage = parse_damage_clause(sentence)
    if damage is not None and damage.expr is not None and (p := _phrase(damage.expr)):
        recipient = damage.to.strip()
        if barred(p, allowed=False) or not (
            _EACH_RE.fullmatch(recipient)
            or _ITS_CONTROLLER_RE.fullmatch(recipient)
            or _TARGET_RE.fullmatch(recipient)
            or _THAT_RE.fullmatch(recipient)
        ):
            return None
        return _Damage(p, recipient)
    mill = parse_mill_clause(sentence)
    if (
        mill is not None
        and mill.kind in ("x", "equal")
        and (p := _phrase(mill.expr or ""))
        and (mill.who in _MILL_WHO or _ITS_CONTROLLER_RE.fullmatch(mill.who))
    ):
        return None if barred(p, allowed=False) else _step_mill(mill.who, p)
    created = parse_create(body) if where is not None else None
    if (
        created is not None
        and created[0] in ("", "you", "that player")
        and re.match(r"^(?:x\s|an? x/x\s)", created[1], re.IGNORECASE)
        and (p := _phrase(tail))
    ):
        if barred(p, allowed=False):
            return None
        make = token_maker(created[1])
        return None if make is None else _step_made_tokens(make, p, who=created[0])
    if (
        where is not None
        and (m := _PUMP_RE.fullmatch(body))
        and (stats := _X_AND_Y_RE.fullmatch(tail))
        and (px := _phrase(stats.group("xstat")))
    ):
        py = _phrase(stats.group("ystat")) if stats.group("ystat") else None
        if stats.group("ystat") and py is None:
            return None
        if barred(px, allowed=m.group("subject").lower().startswith("target creature")):
            return None
        return _step_pump(
            m.group("subject"),
            m.group("power"),
            m.group("toughness"),
            px,
            py,
            m.group("grants") or "",
        )
    put = parse_put_counters(sentence)
    if (
        put is not None
        and put.x
        and put.kind in ("+1/+1", "-1/-1")
        and _COUNTERS_ON_RE.fullmatch(put.on)
        and (p := _phrase(put.expr or ""))
    ):
        return None if barred(p, allowed=True) else _step_counters(put.kind, put.on, p)
    return None


def _opening_step(sentence: str, *, for_spell: bool) -> tuple[ResolutionStep, str | None] | None:
    """An opening sentence that moves something, and the rest of the sentence
    when it carries a ", then ..." tail."""
    if _RETURN_RE.fullmatch(sentence):
        return _step_return_to_hand, None
    if _PUT_ON_TOP_RE.fullmatch(sentence):
        return _step_put_on_top, None
    if m := _EXILE_GRAVEYARD_RE.fullmatch(sentence):
        return _step_exile_from_graveyard, m.group("rest")
    if _COUNTER_RE.fullmatch(sentence):
        return _step_counter_spell, None
    if m := _CONTROLLER_SACRIFICES_RE.fullmatch(sentence):
        return _step_controller_sacrifices, m.group("rest")
    if _EXILE_TOP_RE.fullmatch(sentence):
        return _step_exile_top, None
    if m := _SACRIFICE_RE.fullmatch(sentence):
        step = _step_sacrifice(
            m.group("restriction"), may=bool(m.group("may")), for_spell=for_spell
        )
        return None if step is None else (step, None)
    if _EXILE_TARGET_RE.fullmatch(sentence):
        step = _step_delegate_to_target(f"{sentence}.", for_spell=for_spell)
        return None if step is None else (step, None)
    return None


#: Cheap literal gates ahead of any regex: the text names a characteristic and
#: an object some earlier part of the text or its cost moved.
_GATE_STATS = ("power", "toughness", "mana value", "counters on it")
_GATE_REFERENCES = (
    "sacrificed",
    "exiled",
    "exile",
    "that card",
    "that spell",
    "card returned",
    "card you",
    "counters on it",
    "its power",
    "its toughness",
    "that creature",
)


@functools.cache
def moved_card_stat_effect(text: str, *, for_spell: bool) -> Callable[["Game", Any], None] | None:
    """The effect of `text` when it spends a characteristic of something the
    text itself, or its cost, moved, or `None` for anything else."""
    lowered = text.lower()
    if " equal to " not in lowered and "where x is" not in lowered:
        return None
    if not any(word in lowered for word in _GATE_STATS):
        return None
    if not any(word in lowered for word in _GATE_REFERENCES):
        return None
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble

    sentences = [
        _clean(sentence)
        for sentence in _plain_resolution_sentences(_strip_non_effect_preamble(collapsed(text)))
    ]
    sentences = [s for s in sentences if s and not s.lower().startswith("fuse")]
    if not sentences:
        return None
    last = sentences[-1]
    if (
        last.lower().startswith("exile ")
        and not _EXILE_TARGET_RE.fullmatch(last)
        and not _EXILE_GRAVEYARD_RE.fullmatch(last)
    ):
        return None  # "Exile <this spell>.": the spell reader strips it and asks again
    steps: list[ResolutionStep] = []
    uses_amount = False
    # An opening sentence, possibly with a ", then ..." tail.
    opening = _opening_step(sentences[0], for_spell=for_spell)
    queue = list(sentences)
    if opening is not None:
        steps.append(opening[0])
        queue = ([opening[1]] if opening[1] else []) + sentences[1:]
    damage_steps: list[_Damage] = []
    position = 0
    while position < len(queue):
        sentence = queue[position]
        position += 1
        guard: Callable[[State], bool] | None = None
        if m := _IF_YOU_DO_RE.fullmatch(sentence):
            sentence, guard = m.group("rest"), lambda s: s.did
        elif m := _IF_RETURNED_RE.fullmatch(sentence):
            quality = m.group("quality").lower()
            sentence = m.group("rest")
            guard = _returned_quality(quality)
        elif m := _IF_IT_IS_RE.fullmatch(sentence):
            kind = m.group("kind").lower()
            sentence = m.group("rest")
            guard = lambda s, kind=kind: s.referent is not None and s.referent.is_a(kind)  # noqa: E731
        if m := _DOUBLED_RE.fullmatch(sentence):
            if not damage_steps:
                return None
            damage_steps[-1].doubled_for = m.group("kind").lower()
            continue
        if (
            position < len(queue)
            and (made := _TOKEN_STATS_RE.fullmatch(sentence))
            and (size := _TOKEN_SIZE_RE.fullmatch(queue[position]))
        ):
            power, toughness = _phrase(size.group("power")), _phrase(size.group("toughness"))
            if power is None or toughness is None:
                return None
            step = _step_stat_sized_token(made.group("desc"), (power, toughness))
            position += 1
        else:
            step = _amount_step(sentence, for_spell=for_spell, opener=opening is not None)
        if step is None:
            return None
        if isinstance(step, _Damage):
            damage_steps.append(step)
        uses_amount = True
        steps.append(_guarded(step, guard) if guard is not None else step)
    if not uses_amount:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        state = State()
        for step in steps:
            if not step(game, stack_object, state):
                return

    return effect


def _returned_quality(quality: str) -> Callable[[State], bool]:
    """ "If you return a nonland card to your hand this way": the card moved
    and is not a land."""
    if quality.startswith("non"):
        word = quality[3:]
        return lambda s: s.did and s.referent is not None and not s.referent.is_a(word)
    return lambda s: s.did and s.referent is not None and s.referent.is_a(quality)
