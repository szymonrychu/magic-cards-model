"""EP-02 R3 T7: "for each <thing>" and "equal to the number of <things>" counts
that are not a permanent or card in a zone: a per-turn history, a cast record,
the Curses attached to a player, the distinct mana values on a board.

`for_each_cards_counts` is the one reader `amounts._for_each_multiplier` asks
first; `number_of_cards_counts` is the `(game, controller) -> int` twin
`amounts.count_expression` asks first. Both only chain the sub-readers listed
in `_FOR_EACH` / `_NUMBER_OF`, each a `functools.cache`d pure function of the
phrase that returns `None` for a phrase it does not read - so a phrase
travels the chain once and the answer is remembered (the classify budget).
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, ORDINAL, parse_count, parse_ordinal
from .effects._chains import FORWARD, MIXED_CLAUSE, MIXED_CLAUSES

if TYPE_CHECKING:
    from ..models.game import Game

#: `(game, controller, source_id) -> int`: `amounts._for_each_multiplier`'s form.
ForEach = Callable[["Game", str, "str | None"], int]
#: `(game, controller) -> int`: `amounts.count_expression`'s form.
NumberOf = Callable[["Game", str], int]


_DIED_SUFFIX = " that died this turn"


def _died_this_turn_each(phrase: str) -> ForEach | None:
    """ "for each creature that died this turn" / "for each Zubera that died
    this turn": the same count as "the number of creatures that died this
    turn" (`amounts._COUNT_DIED_THIS_TURN_RE`, read off the turn's
    "to_graveyard" history, CR 700.4), taken once as the effect applies
    (CR 608.2h)."""
    if not phrase.lower().endswith(_DIED_SUFFIX):
        return None
    from .effects.amounts import count_expression

    head = phrase[: -len(_DIED_SUFFIX)]
    counted = count_expression(f"the number of {head}{_DIED_SUFFIX}") or count_expression(
        f"the number of {head}s{_DIED_SUFFIX}"
    )
    if counted is None:
        return None
    return lambda game, controller, _source_id: counted(game, controller)


# --------------------------------------------------------------------------
# Who "target opponent" / "that player" / "they" names while it resolves
# --------------------------------------------------------------------------


def _event_player(game: "Game", controller: str) -> str:
    """The player the resolving trigger's event concerns (CR 603.2): "that
    player" of "At the beginning of enchanted player's upkeep ... that player",
    else the controller (CR 109.5)."""
    event = getattr(game.resolving, "event", None)
    if event is not None and event.player is not None:
        return event.player
    return controller


def _targeted_player(game: "Game", controller: str) -> str:
    """The first player the resolving object targets, else the controller."""
    from .ep02_r1_graveyard_counts import _referent_player

    return _referent_player(game, controller)


# --------------------------------------------------------------------------
# "cards target opponent discarded this turn" (CR 701.9a)
# --------------------------------------------------------------------------

_DISCARDED_RE = re.compile(
    r"^(?:the )?(?:number of )?cards? (?P<who>target opponent|target player|that player|an opponent"
    r"|each opponent|they) (?:has |have )?discarded this turn$",
    re.IGNORECASE,
)


def _cards_discarded_this_turn(phrase: str) -> NumberOf | None:
    """The cards a player other than "you" discarded this turn
    (`Game.cards_discarded_this_turn`, cycling counted: CR 702.29a), the
    player the printed words name; "each opponent" is the sum over them."""
    if (
        "discarded this turn" not in phrase.lower()
        or (match := _DISCARDED_RE.fullmatch(phrase)) is None
    ):
        return None
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        ledger = game.cards_discarded_this_turn
        if who in ("each opponent", "an opponent"):
            return sum(
                ledger.get(p.username, 0) for p in game.players_in_game if p.username != controller
            )
        if who in ("that player", "they"):
            return ledger.get(_event_player(game, controller), 0)
        return ledger.get(_targeted_player(game, controller), 0)

    return count


# --------------------------------------------------------------------------
# "Goblins that entered the battlefield under your control this turn"
# --------------------------------------------------------------------------

_ENTERED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<quality>[a-z][a-z ,'-]*?) that entered the battlefield "
    r"under your control this turn$",
    re.IGNORECASE,
)


def _entered_under_your_control(phrase: str) -> NumberOf | None:
    """The permanents of a description that entered the battlefield under the
    controller's control this turn (CR 603.6a: entering is a fact of the turn,
    the turn's "entered" history keeps the object as it entered), counting the
    ones that have since left."""
    if " that entered the battlefield under your control this turn" not in phrase.lower():
        return None
    match = _ENTERED_RE.fullmatch(phrase)
    if match is None:
        return None
    from .conditions.history import _quality

    quality = _quality(match.group("quality"))
    if quality is None:
        return None
    return lambda game, controller: sum(
        1
        for entry in game.turn_history
        if entry.kind == "entered" and entry.player == controller and quality(entry)
    )


# --------------------------------------------------------------------------
# "different mana value among nonland permanents you control" (CR 202.3)
# --------------------------------------------------------------------------

_DIFFERENT_MV_RE = re.compile(
    r"^(?:the )?(?:number of )?different mana values? among (?P<quality>[a-z][a-z ,'-]*?) "
    r"you control$",
    re.IGNORECASE,
)


def _different_mana_values_among_permanents(phrase: str) -> NumberOf | None:
    """How many distinct mana values the permanents of a description the
    controller controls have, off the computed board (CR 613.5); a permanent
    with no mana cost is mana value 0 (CR 202.3a)."""
    if (
        "different mana value" not in phrase.lower()
        or (match := _DIFFERENT_MV_RE.fullmatch(phrase)) is None
    ):
        return None
    from ..models.game import _permanent_quality

    quality = _permanent_quality(match.group("quality"))
    if quality is None:
        return None

    def count(game: "Game", controller: str) -> int:
        board = game.computed_board()
        values = set()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller == controller and quality(chars):
                values.add(int(chars.mana_value))
        return len(values)

    return count


# --------------------------------------------------------------------------
# Multikicker: "each time it was kicked", "the number of times that spell was kicked"
# --------------------------------------------------------------------------


def _times_kicked_each(phrase: str) -> ForEach | None:
    """ "for each time it was kicked" (Bloodhusk Ritualist): CR 702.33d's count
    off the cast record of the source permanent, which CR 400.7d lets an
    ability of the permanent read."""
    if phrase.lower() not in ("time it was kicked", "time this creature was kicked"):
        return None

    def count(game: "Game", _controller: str, source_id: str | None) -> int:
        source = None if source_id is None else game.find_by_id(UUID(source_id))
        record = game.cast_record_of(source) if isinstance(source, CardState) else None
        return record.kicked if record is not None else 0

    return count


_SPELL_KICKED_RE = re.compile(r"^(?:the )?number of times that spell was kicked$", re.IGNORECASE)


def _times_that_spell_was_kicked(phrase: str) -> NumberOf | None:
    """ "the number of times that spell was kicked" (a cast trigger's spell,
    CR 702.33d), off the record of the spell the cast event names - kept for a
    spell that has since resolved or been countered (CR 608.2h)."""
    if "was kicked" not in phrase.lower() or _SPELL_KICKED_RE.fullmatch(phrase) is None:
        return None

    def count(game: "Game", _controller: str) -> int:
        event = getattr(game.resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        spell = game.find_by_id(event.subject_id)
        record = game.cast_record_of(spell) if isinstance(spell, CardState) else None
        if record is None and event.subject_stamp is not None:
            record = game.cast_record_as_last_known(event.subject_stamp)
        return record.kicked if record is not None else 0

    return count


# --------------------------------------------------------------------------
# "the number of Curses attached to that player" (CR 303.4m, CR 701.3a)
# --------------------------------------------------------------------------

_CURSES_RE = re.compile(
    r"^(?:the )?number of (?P<kind>[A-Za-z]+?)s? attached to (?P<who>them|that player|you|"
    r"enchanted player)$",
    re.IGNORECASE,
)


def _auras_attached_to_player(phrase: str) -> NumberOf | None:
    """How many permanents of a subtype ("Curses") are attached to a player: an
    Aura enchanting a player is attached to it (CR 303.4m, CR 701.3a). "Them"
    is the player the reader is asked for (the one an enclosing "deals damage
    to that player" counts for); "that player" the resolving trigger's."""
    if " attached to " not in phrase.lower() or (match := _CURSES_RE.fullmatch(phrase)) is None:
        return None
    kind = match.group("kind").lower()
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        player = _event_player(game, controller) if who == "that player" else controller
        board = game.computed_board()
        return sum(
            1
            for permanent in game.battlefield
            if permanent.attachment is not None
            and permanent.attachment.username == player
            and any(subtype.lower() == kind for subtype in board.of(permanent).subtypes)
        )

    return count


# --------------------------------------------------------------------------
# "for each Aura you controlled that was attached to it" (CR 603.10a)
# --------------------------------------------------------------------------

_ATTACHED_TO_IT_EACH_RE = re.compile(
    r"^(?P<kind>[a-z]+) you controlled that was attached to it$", re.IGNORECASE
)


def _attachments_it_had_each(phrase: str) -> ForEach | None:
    """ "for each Aura you controlled that was attached to it" (a dies trigger,
    Hateful Eidolon): the Auras the dying permanent had as it last existed on
    the battlefield (CR 603.10a), `CardState.last_known_attachments`, that the
    controller controlled."""
    if (
        " that was attached to it" not in phrase.lower()
        or (match := _ATTACHED_TO_IT_EACH_RE.fullmatch(phrase)) is None
    ):
        return None
    kind = match.group("kind").lower()

    def count(game: "Game", controller: str, _source_id: str | None) -> int:
        event = getattr(game.resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        dead = game.find_by_id(event.subject_id)
        if not isinstance(dead, CardState):
            return 0
        return sum(
            1
            for snapshot in dead.last_known_attachments
            if snapshot.controller == controller
            and any(subtype.lower() == kind for subtype in snapshot.subtypes)
        )

    return count


# --------------------------------------------------------------------------
# "the number of red mana symbols in the sacrificed creature's mana cost" (CR 107.4e)
# --------------------------------------------------------------------------

_SACRIFICED_SYMBOLS_RE = re.compile(
    r"^(?:the )?number of (?P<color>white|blue|black|red|green) mana symbols? in "
    r"the sacrificed (?:creature|permanent)'s mana cost$",
    re.IGNORECASE,
)


def _mana_symbols_in_sacrificed_cost(phrase: str) -> NumberOf | None:
    """How many mana symbols of one color the mana cost of what the resolving
    object's cost sacrificed has (Fiery Bombardment's Chroma ability). A
    hybrid symbol is also a symbol of each of its colors (CR 107.4e). The
    sacrificed card is read where the cost left it (CR 608.2h); a token has no
    mana cost to count."""
    if (
        "mana cost" not in phrase.lower()
        or (match := _SACRIFICED_SYMBOLS_RE.fullmatch(phrase)) is None
    ):
        return None
    from ..models.card import Color
    from ..models.mana import ManaCost

    color = {
        "white": Color.WHITE,
        "blue": Color.BLUE,
        "black": Color.BLACK,
        "red": Color.RED,
        "green": Color.GREEN,
    }[match.group("color").lower()]

    def count(game: "Game", _controller: str) -> int:
        resolving = game.resolving
        ids = getattr(resolving, "cost_sacrificed_card_ids", ())
        if not ids and isinstance(resolving, CardState):
            record = game.cast_record_of(resolving)
            ids = tuple(record.additional_cost_cards) if record is not None else ()
        total = 0
        for card_id in ids[:1]:
            card = game.find_by_id(card_id)
            if card is not None and card.mana_cost:
                total += sum(
                    1 for symbol in ManaCost.parse(card.mana_cost).symbols if color in symbol.colors
                )
        return total

    return count


_FOR_EACH_READERS = (
    _died_this_turn_each,
    _times_kicked_each,
    _attachments_it_had_each,
)
_NUMBER_OF_READERS = (
    _cards_discarded_this_turn,
    _entered_under_your_control,
    _different_mana_values_among_permanents,
    _times_that_spell_was_kicked,
    _auras_attached_to_player,
    _mana_symbols_in_sacrificed_cost,
)


def _as_for_each(reader: NumberOf) -> ForEach:
    return lambda game, controller, _source_id: reader(game, controller)


@cache
def for_each_cards_counts(phrase: str) -> ForEach | None:
    """The count of "<effect> for each <phrase>", or `None`."""
    text = " ".join(phrase.split())
    for reader in _FOR_EACH_READERS:
        if (count := reader(text)) is not None:
            return count
    # The same description counted as "the number of <description>".
    for number_reader in _NUMBER_OF_READERS:
        if (counted := number_reader(text) or number_reader(f"the number of {text}")) is not None:
            return _as_for_each(counted)
    return None


@cache
def number_of_cards_counts(phrase: str) -> NumberOf | None:
    """The count of "the number of <phrase>" / "equal to <phrase>", or `None`."""
    text = " ".join(phrase.split())
    for reader in _NUMBER_OF_READERS:
        if (count := reader(text)) is not None:
            return count
    return None


# --------------------------------------------------------------------------
# "any number of target players other than that player each draw cards equal to ..."
# --------------------------------------------------------------------------

_PLAYERS_EACH_DRAW_RE = re.compile(
    rf"^(?P<players>any number of|up to {COUNT}|{COUNT}) target players"
    r"(?P<other> other than that player)? each draws? "
    rf"(?:(?P<n>{COUNT}) cards?|cards equal to (?P<expr>.+))$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_players_each_draw_equal_clause(clause: str, *, for_spell: bool) -> Any:
    """ "Any number of target players other than that player each draw cards
    equal to the number of Curses attached to that player." (Curse of
    Surveillance): each chosen player draws the one amount, counted once as the
    ability resolves (CR 608.2h) - for the controller (CR 109.5), whose "that
    player" is the enchanted player of the trigger's event. A target no longer
    legal draws nothing (CR 608.2b); "any number" may choose no one (CR 107.1c).
    """
    text = " ".join(clause.split()).rstrip(".")
    if " each draw" not in text.lower() or "target players" not in text.lower():
        return None
    match = _PLAYERS_EACH_DRAW_RE.fullmatch(text)
    if match is None or (match.group("n") is None) == (match.group("expr") is None):
        return None
    from .effects._common import _targets_understood

    phrase = f"{match.group('players')} target players{match.group('other') or ''}"
    if not _targets_understood(phrase, allow_player_targets=True, count_agnostic=True):
        return None
    if match.group("n") is not None:
        fixed = parse_count(match.group("n"))
        if fixed is None:
            return None
        amount_of = lambda _game, _controller: fixed  # noqa: E731
    else:
        from .effects.amounts import count_expression

        amount_of = count_expression(match.group("expr"))
        if amount_of is None:
            return None

    def effect(game: "Game", stack_object: Any) -> None:
        amount = amount_of(game, game.controller_of(stack_object).username)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player) and amount > 0:
                game.draw_cards(target.username, amount)

    return effect


# --------------------------------------------------------------------------
# "<verb> target X if its mana value is less than or equal to the number of <Y>"
# --------------------------------------------------------------------------

_IF_MV_AT_MOST_COUNT = r"if its mana value is less than or equal to (?P<expr>the number of [^.]+)"
_DESTROY_IF_MV_RE = re.compile(
    rf"^destroy (?P<phrase>target [^.]+?) {_IF_MV_AT_MOST_COUNT}$", re.IGNORECASE
)
_PUT_ONTO_BATTLEFIELD_IF_MV_RE = re.compile(
    r"^put (?P<phrase>target [^.]+? card from [^.]+?graveyard) onto the battlefield"
    rf"(?P<yours> under your control)? {_IF_MV_AT_MOST_COUNT}$",
    re.IGNORECASE,
)


def _target_within_count(
    match: "re.Match[str]", *, battlefield_only: bool
) -> tuple[Callable[["Game", str], int], str] | None:
    """The count and the target phrase of a `_IF_MV_AT_MOST_COUNT` clause, or
    `None` when either is not one the engine reads."""
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression

    phrase = match.group("phrase")
    counted = count_expression(match.group("expr"))
    if counted is None or not _targets_understood(phrase, battlefield_only=battlefield_only):
        return None
    return counted, phrase


def _targets_within_count(game: "Game", stack_object: Any, counted: Callable[..., int]) -> list:
    """The resolving object's legal card targets (CR 608.2b) whose mana value
    (CR 202.3) is within the count, taken once as the instruction is followed
    (CR 608.2c, CR 608.2h)."""
    limit = counted(game, game.controller_of(stack_object).username)
    return [
        target
        for target in game.resolve_targets(stack_object)
        if isinstance(target, CardState) and game.characteristics_of(target).mana_value <= limit
    ]


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_destroy_target_if_mana_value_within_count(clause: str, *, for_spell: bool) -> Any:
    """ "Destroy target artifact or enchantment if its mana value is less than
    or equal to the number of cards in your hand." (Rending Vines): the target
    is any artifact or enchantment (CR 115.1); the "if" gates the destruction
    (CR 701.8a) as it is followed, so a permanent above the count is left
    alone."""
    if " if its mana value is less than or equal to the number of " not in clause.lower():
        return None
    match = _DESTROY_IF_MV_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    read = None if match is None else _target_within_count(match, battlefield_only=True)
    if read is None:
        return None
    counted, _phrase = read

    def effect(game: "Game", stack_object: Any) -> None:
        for target in _targets_within_count(game, stack_object, counted):
            if target.zone is Zone.BATTLEFIELD:
                game.destroy(target)

    return effect


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_put_graveyard_card_if_mana_value_within_count(clause: str, *, for_spell: bool) -> Any:
    """ "Put target creature card from an opponent's graveyard onto the
    battlefield under your control if its mana value is less than or equal to
    the number of Allies you control." (Agadeem Occultist): the card enters
    under the controller's control when the printed words say so (CR 110.2a),
    else under its owner's."""
    if " if its mana value is less than or equal to the number of " not in clause.lower():
        return None
    match = _PUT_ONTO_BATTLEFIELD_IF_MV_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    read = None if match is None else _target_within_count(match, battlefield_only=False)
    if read is None:
        return None
    counted, _phrase = read
    yours = match.group("yours") is not None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = game.controller_of(stack_object).username
        for target in _targets_within_count(game, stack_object, counted):
            if target.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(target, controller if yours else target.owner)

    return effect


_RETURN_TO_BATTLEFIELD_FRONTED_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — |[a-z][a-z '-]* - )?return to the battlefield "
    r"(?P<phrase>target [^.]+? card in your graveyard(?: with [^.]+)?)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_return_to_the_battlefield_target_in_your_graveyard(
    clause: str, *, for_spell: bool
) -> Any:
    """ "Return to the battlefield target nonland permanent card in your
    graveyard with mana value less than or equal to the number of permanent
    cards in your graveyard." (Squirming Emergence): `_RETURN_FROM_YOUR_
    GRAVEYARD_TO_BATTLEFIELD_RE`'s verb with the destination fronted. The mana
    value bound is a targeting restriction (CR 115.1, CR 601.2c) that
    `targeting.py` enforces, and is checked again as the spell resolves (CR
    608.2b); the card returns under its owner's control (CR 110.2)."""
    match = _RETURN_TO_BATTLEFIELD_FRONTED_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(target, target.owner)

    return effect


# --------------------------------------------------------------------------
# One-shot "gets +P/+T until end of turn" over a count taken as it applies
# --------------------------------------------------------------------------


def _pump_until_end_of_turn(
    game: "Game", stack_object: Any, subject: CardState, power: int, toughness: int
) -> None:
    """A CR 611.2 one-shot effect: `subject` (this incarnation of it only, CR
    400.7) gets `power`/`toughness` until end of turn, in layer 7c (CR 613.4c,
    so it adds to any other pump)."""
    from .effects.continuous import continuous_effects
    from .layers import (
        ContinuousEffect,
        Duration,
        Layer,
        Sublayer,
        modify_power_toughness,
        only_this_incarnation,
    )

    if subject.zone is not Zone.BATTLEFIELD or (power == 0 and toughness == 0):
        return
    store = continuous_effects(game)
    store.add(
        ContinuousEffect(
            description=f"{subject.name}: gets {power:+d}/{toughness:+d} until end of turn",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=store.tick(),
            duration=Duration.UNTIL_END_OF_TURN,
            source_id=getattr(stack_object, "source_id", None),
            selector=only_this_incarnation(subject, subject.zone_change_stamp),
            modification=modify_power_toughness(power, toughness),
        )
    )


# --------------------------------------------------------------------------
# "it gets +1/+0 until end of turn for each other attacking creature that shares
# a creature type with it" (Shared Animosity, CR 508.1, CR 205.3m)
# --------------------------------------------------------------------------

_ATTACKER_SHARING_PUMP_RE = re.compile(
    r"^it gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn for each other "
    r"attacking creature that shares a creature type with it$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_attacker_pump_per_other_attacker_sharing_a_type(clause: str, *, for_spell: bool) -> Any:
    """Shared Animosity: "Whenever a creature you control attacks, it gets
    +1/+0 until end of turn for each other attacking creature that shares a
    creature type with it." "It" is the creature the trigger's event names
    (CR 603.2); the other attackers are counted once as the ability resolves
    (CR 608.2h), a changeling sharing every type (CR 702.73a)."""
    match = _ATTACKER_SHARING_PUMP_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        from .targeting import _creature_types_overlap, _shareable_creature_types

        event = getattr(stack_object, "event", None)
        subject = (
            None if event is None or event.subject_id is None else game.find_by_id(event.subject_id)
        )
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        own = _shareable_creature_types(subject, game)
        if own is None:
            return
        count = 0
        for other in game.attacking_creatures():
            if other.id == subject.id:
                continue
            types = _shareable_creature_types(other, game)
            if types is not None and _creature_types_overlap(own, types):
                count += 1
        _pump_until_end_of_turn(game, stack_object, subject, power * count, toughness * count)

    return effect


# --------------------------------------------------------------------------
# "<source> deals damage to each of those creatures equal to the number of
# attacking creatures" (Lightmine Field, CR 120.3, CR 508.1)
# --------------------------------------------------------------------------

_DAMAGE_EACH_OF_THOSE_ATTACKERS_RE = re.compile(
    r"^(?P<source>this [a-z]+) deals damage to each of those creatures equal to "
    r"(?P<expr>the number of attacking creatures)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_damage_to_each_batched_attacker_by_attacker_count(
    clause: str, *, for_spell: bool
) -> Any:
    """Lightmine Field: "Whenever one or more creatures attack, this
    enchantment deals damage to each of those creatures equal to the number of
    attacking creatures." "Those creatures" are the attackers the trigger's
    own condition counts (CR 508.3d); the amount is taken once (CR 608.2h) and
    dealt by the source to each at the same time (CR 120.1)."""
    match = _DAMAGE_EACH_OF_THOSE_ATTACKERS_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None or for_spell:
        return None
    from .effects.amounts import count_expression

    counted = count_expression(match.group("expr"))
    if counted is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.damage import _deal_all, _resolving_source
        from .triggers.collect import batched_attackers

        source = _resolving_source(game, stack_object)
        ability = getattr(stack_object, "ability", None)
        if source is None or ability is None:
            return
        controller = game.controller_of(stack_object).username
        attackers = batched_attackers(game, ability.condition, controller)
        if not attackers:
            return
        amount = counted(game, controller)
        _deal_all(game, [(source, attacker, amount) for attacker in attackers])

    return effect


# --------------------------------------------------------------------------
# "Target creature gets -2/-2 until end of turn. It gets an additional -1/-1
# until end of turn for each Desert you control." (Desert's Due, CR 613.4c)
# --------------------------------------------------------------------------

_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=\.)\s+(?=[A-Z])|\n+")
_ADDITIONAL_PUMP_FOR_EACH_RE = re.compile(
    r"^(?:it|that creature) gets an additional (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn for each (?P<each>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_target_pump_then_additional_pump_for_each(text: str, *, for_spell: bool) -> Any:
    """A pump sentence, then "It gets an additional P/T until end of turn for
    each <thing>": "it" is the creature the first sentence pumped. The first
    sentence is read by the ordinary clause reader; the second is a second
    layer 7c modification (CR 613.4c, "an additional" names no new rule) whose
    count is taken once as it applies (CR 608.2h). A target no longer legal
    (CR 608.2b) gets neither."""
    sentences = [part for part in _SENTENCE_BOUNDARY_RE.split(text.strip()) if part.strip()]
    if len(sentences) != 2 or " an additional " not in sentences[1].lower():
        return None
    match = _ADDITIONAL_PUMP_FOR_EACH_RE.fullmatch(sentences[1].strip())
    if match is None:
        return None
    from .effects.amounts import _for_each_multiplier
    from .effects.dispatch import _parse_mixed_clauses

    multiplier = _for_each_multiplier(match.group("each"))
    first = _parse_mixed_clauses(sentences[0], for_spell=for_spell)
    if multiplier is None or first is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        for clause in first:
            clause(game, stack_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction
        count = multiplier(game, game.controller_of(stack_object).username, None)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                _pump_until_end_of_turn(
                    game, stack_object, target, power * count, toughness * count
                )

    return [effect]


# --------------------------------------------------------------------------
# "Target player creates X 2/2 black Zombie creature tokens, then up to one
# target creature gets -1/-1 until end of turn for each Zombie that player
# controls." (Dark Salvation, CR 111.2, CR 608.2c)
# --------------------------------------------------------------------------

_PLAYER_TOKENS_THEN_PUMP_RE = re.compile(
    rf"^(?P<who>target player) creates (?P<n>x|\d+|{COUNT}) (?P<desc>.+?) tokens?, "
    r"then (?P<victim>up to one target creature) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
    r"until end of turn for each (?P<each>[A-Za-z]+) that player controls$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_player_creates_tokens_then_pump_per_their_kind(text: str, *, for_spell: bool) -> Any:
    """Dark Salvation. The player target creates the tokens and controls them
    (CR 111.2); the creature target - the second target in the text's order
    (CR 601.2c) - then gets the pump, counted once, after the tokens exist, on
    that player's board (CR 608.2c, CR 608.2h). No creature chosen ("up to
    one", CR 115.6) is a legal announcement that only makes the tokens."""
    match = _PLAYER_TOKENS_THEN_PUMP_RE.fullmatch(" ".join(text.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression
    from .effects.tokens import _token_definition_from_words

    if not _targets_understood(match.group("who"), allow_player_targets=True):
        return None
    if not _targets_understood(match.group("victim"), count_agnostic=True):
        return None
    definition = _token_definition_from_words(match.group("desc"), None)
    counted = count_expression(f"the number of {match.group('each')}s you control")
    if definition is None or counted is None:
        return None
    x_count = match.group("n").lower() == "x"
    fixed = None if x_count else parse_count(match.group("n"))
    if not x_count and fixed is None:
        return None
    power = int(match.group("power"))
    toughness = int(match.group("toughness"))

    def effect(game: "Game", stack_object: Any) -> None:
        from ..models.token import create_tokens
        from .effects.damage import _announced_x

        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        if not players:
            return
        player = players[0]
        amount = _announced_x(game, stack_object) if x_count else fixed
        if amount:
            create_tokens(game, definition, player.username, amount)
        count = counted(game, player.username)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                _pump_until_end_of_turn(
                    game, stack_object, target, power * count, toughness * count
                )

    return [effect]


# --------------------------------------------------------------------------
# "Draw a card for each creature target player controls, then draw a card for each
# creature another target player controls." (Biomantic Mastery, CR 608.2c)
# --------------------------------------------------------------------------

_DRAW_FOR_EACH_TARGET_PLAYERS_RE = re.compile(
    r"^draw a card for each (?P<first>[a-z][a-z ]*?) (?P<one>target player) controls, "
    r"then draw a card for each (?P<second>[a-z][a-z ]*?) "
    r"(?P<other>another target player) controls$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_draw_for_each_thing_two_target_players_control(text: str, *, for_spell: bool) -> Any:
    """Biomantic Mastery. Two different player targets (CR 115.3: "another"),
    in the order the text names them (CR 601.2c). The controller draws, one
    card for each thing the first player controls, then one for each thing the
    second controls - each count taken as that draw is performed (CR 608.2c,
    CR 608.2h). A player no longer a legal target contributes nothing (CR
    608.2b)."""
    match = _DRAW_FOR_EACH_TARGET_PLAYERS_RE.fullmatch(" ".join(text.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.amounts import count_expression

    if not (
        _targets_understood("target player", allow_player_targets=True)
        and _targets_understood("another target player", allow_player_targets=True)
    ):
        return None
    counts = [
        count_expression(f"the number of {match.group(group)}s you control")
        for group in ("first", "second")
    ]
    if any(counted is None for counted in counts):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        drawer = game.controller_of(stack_object).username
        for counted, reference in zip(counts, stack_object.targets, strict=False):
            player = game.legal_target(stack_object, reference)
            if isinstance(player, Player):
                game.draw_cards(drawer, counted(game, player.username))
                game.announce_batched_events()  # CR 603.2c: one event per instruction

    return [effect]


# --------------------------------------------------------------------------
# "For each attacking creature, its owner puts it on their choice of the top or
# bottom of their library." (Aetherspouts, CR 401.1, CR 608.2d)
# --------------------------------------------------------------------------

_FOR_EACH_OWNER_PUTS_IT_RE = re.compile(
    r"^for each (?P<what>[a-z][a-z ]*?), its owner puts it on their choice of the top or "
    r"bottom of their library$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_permanent_its_owner_puts_it_top_or_bottom(
    clause: str, *, for_spell: bool
) -> Any:
    """Aetherspouts. The group is fixed as the instruction begins (CR 608.2f);
    each one's owner - not the controller - makes their own top-or-bottom
    choice for it (CR 108.3, CR 608.2d), and it moves from the battlefield to
    that library (CR 401.1)."""
    match = _FOR_EACH_OWNER_PUTS_IT_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .targeting import permanent_description

    requirement = permanent_description(match.group("what"))
    if requirement is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .decisions import Decision, DecisionKind, source_id_of

        controller = game.controller_of(stack_object).username
        source = stack_object.name if for_spell else stack_object.source_name
        group = [
            permanent
            for permanent in list(game.battlefield)
            if requirement.rejects(permanent, controller, game) is None
        ]
        for permanent in group:
            if permanent.zone is not Zone.BATTLEFIELD or permanent.owner is None:
                continue
            top = game.ask(
                Decision(
                    kind=DecisionKind.PUT_ON_TOP_OR_BOTTOM,
                    player=permanent.owner,
                    prompt=(
                        f"put {permanent.name} on the top or bottom of {permanent.owner}'s library"
                    ),
                    source=source,
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(top, bool)
            game.put_cards_into_library([permanent], to_bottom=not top)

    return effect


# --------------------------------------------------------------------------
# "for each opponent, put up to one target <X> that player controls into its
# owner's library third from the top" (Riptide Gearhulk, CR 401.1, CR 115.6)
# --------------------------------------------------------------------------

_FOR_EACH_OPPONENT_TO_LIBRARY_RE = re.compile(
    rf"^for each opponent, put up to one target (?P<desc>.+?) that player controls into its "
    rf"owner'?s library (?P<ordinal>{ORDINAL}) from the top$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_opponent_put_into_library_nth_from_top(clause: str, *, for_spell: bool) -> Any:
    """Riptide Gearhulk. One optional target per opponent (the profile is
    `targeting._for_each_opponent_profile`'s); each permanent still on the
    battlefield goes into its *owner's* library at the printed depth (CR 401.1;
    CR 609.3: a library shorter than that takes it as deep as it goes)."""
    match = _FOR_EACH_OPPONENT_TO_LIBRARY_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.continuous import _for_each_opponent_target_phrase
    from .effects.returns import _reposition_in_owners_library

    depth = parse_ordinal(match.group("ordinal"))
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if depth is None or not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                moved = game.put_cards_into_library([target])
                for card in moved:
                    _reposition_in_owners_library(game, card, depth=depth - 1)

    return effect


# --------------------------------------------------------------------------
# "for each opponent, you may put up to one target creature card from that
# player's graveyard onto the battlefield under your control" (Sepulchral
# Primordial, CR 110.2a, CR 608.2d)
# --------------------------------------------------------------------------

_FOR_EACH_OPPONENT_REANIMATE_RE = re.compile(
    r"^for each opponent, you may put up to one target (?P<desc>.+?) from that player'?s "
    r"graveyard onto the battlefield under your control$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_for_each_opponent_may_reanimate_from_their_graveyard(
    clause: str, *, for_spell: bool
) -> Any:
    """Sepulchral Primordial. One optional target per opponent, a card in
    that opponent's graveyard (`targeting._for_each_opponent_profile`); the
    controller chooses, for each, whether to put it onto the battlefield under
    their control (CR 608.2d, CR 110.2a). A card that has left the graveyard
    is no longer a legal target (CR 608.2b)."""
    match = _FOR_EACH_OPPONENT_REANIMATE_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(
        f"up to one target {match.group('desc')} from an opponent's graveyard",
        count_agnostic=True,
        battlefield_only=False,
    ):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .decisions import source_id_of

        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            if game.may(
                controller,
                f"put {target.name} onto the battlefield under your control",
                source=source,
                source_id=source_id_of(stack_object),
                cards=[target],
            ):
                game.put_onto_battlefield(target, controller.username)

    return effect


# --------------------------------------------------------------------------
# "Destroy up to three other target nonland permanents. For each of those
# permanents, its controller creates a 3/3 white Angel creature token with
# flying." (Soul of Emancipation, CR 701.8a, CR 111.2)
# --------------------------------------------------------------------------

_DESTROY_THEN_CONTROLLERS_CREATE_RE = re.compile(
    rf"^destroy (?P<phrase>up to (?:{COUNT}) other target [^.]+?)\. "
    r"for each of those (?:permanents|creatures), its controller creates "
    r"(?:an?|one) (?P<desc>.+?) tokens?(?: with (?P<tail>[^.]+))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_destroy_targets_then_each_controller_creates_a_token(
    text: str, *, for_spell: bool
) -> Any:
    """Soul of Emancipation. The destroyed permanents' controllers are read
    before they die (CR 608.2h last-known information: the permanents are gone
    afterwards), then each of them creates the token (CR 111.2). "Each of those
    permanents" is every legal target, one token per permanent whether or not
    destruction happened (an indestructible one is still one of those
    permanents)."""
    match = _DESTROY_THEN_CONTROLLERS_CREATE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    from .effects._common import _targets_understood
    from .effects.tokens import _token_definition_from_words

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    tail = match.group("tail")
    definition = _token_definition_from_words(match.group("desc"), tail.strip() if tail else None)
    if definition is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from ..models.token import create_tokens

        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        controllers = [game.controller_of(target).username for target in targets]
        for target in targets:
            if target.zone is Zone.BATTLEFIELD:
                game.destroy(target)
        game.announce_batched_events()  # CR 603.2c: one event per instruction
        for username in controllers:
            create_tokens(game, definition, username, 1)

    return [effect]


# --------------------------------------------------------------------------
# "For each planeswalker you control, you may activate one of its loyalty
# abilities once this turn as though none of its loyalty abilities have been
# activated this turn." (The Chain Veil, CR 606.3)
# --------------------------------------------------------------------------

_EXTRA_LOYALTY_ACTIVATION_RE = re.compile(
    r"^for each planeswalker you control, you may activate one of its loyalty abilities once "
    r"this turn as though none of its loyalty abilities have been activated this turn$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_each_planeswalker_may_activate_a_loyalty_ability_again(
    clause: str, *, for_spell: bool
) -> Any:
    """The Chain Veil. CR 606.3 allows one loyalty activation per planeswalker
    each turn, counted on `Game.loyalty_activations`; "as though none of its
    loyalty abilities have been activated this turn" frees exactly one more
    activation (the text says "once"), for each planeswalker the controller
    controls as the ability resolves (CR 608.2h). Nothing is written for a
    planeswalker whose limit is not used up, and the "may" is the controller's
    to leave unused - the permission costs nothing to hold."""
    if (
        for_spell
        or _EXTRA_LOYALTY_ACTIVATION_RE.fullmatch(" ".join(clause.split()).rstrip(".")) is None
    ):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        from .equip_block_statics import loyalty_activation_limit

        controller = game.controller_of(stack_object).username
        for walker in game.permanents_controlled_by(controller):
            if Type.PLANESWALKER not in game.characteristics_of(walker).types:
                continue
            limit = max(
                game._loyalty_activations_allowed(walker),  # noqa: SLF001
                loyalty_activation_limit(game, controller),
            )
            key = str(walker.id)
            used = game.loyalty_activations.get(key, 0)
            game.loyalty_activations[key] = min(used, limit - 1)

    return effect
