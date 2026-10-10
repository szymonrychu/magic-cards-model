"""Turn-history conditions: what happened this turn (or last turn) - attacks,
crews, deaths, zone changes, permanents entering, life gained and lost, damage
dealt, energy paid, spells cast, lands played, discards, draws, sacrifices,
counters put, loyalty abilities and crimes.

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

**Recording.** `record(game, event)` is called by `Game.emit` for every event
the game raises, before any trigger is looked for, so a fact this family needs
that no existing ledger keeps is written from the event that carries it: into
`Game.turn_history` (`TurnHistoryEntry`, one per permanent entering, going to
a graveyard or a hand from the battlefield, sacrificed, attacking or crewing,
with its characteristics at that moment), `Game.turn_counts`
(`Game.note_turn_count`), `Game.turn_facts` (`Game.record_turn_fact`) or
`Game.damage_dealt_this_turn`. The few facts no event carries are recorded by
`Game` where the action happens, through the helpers below: a crime as the
spell or ability with its targets goes on the stack (`record_crime`), energy
paid (`models/game.ENERGY_PAID_OR_LOST`), excess damage as it is dealt
(`excess_damage`), and cards put into exile (`note_exile_arrivals`, which
also runs on every event). `end_turn` closes a turn off before its ledgers
roll, so "last turn" is read from `turn_counts_last_turn` and
`turn_history_last_turn`.

Rules verified with `mise run rules:find`:

- CR 119.3 (an effect makes a player lose life) and CR 120.3a (damage dealt
  to a player causes that much life loss) - `Player.life_lost_this_turn`
  counts both.
- CR 120.1: "An object that deals damage is the source of that damage."
- CR 120.2a / 120.2b: combat and noncombat damage.
- CR 120.6: lethal damage takes the damage already marked into account.
- CR 120.10: excess damage - more than lethal damage to a creature, more than
  its loyalty to a planeswalker, more than its defense to a battle; the
  greatest of those for a permanent of several of the types.
- CR 702.2c: combat damage from a source with deathtouch - any nonzero amount
  is lethal damage for excess damage.
- CR 109.2b: a description with the word "spell" means a spell on the stack.
- CR 603.10a: a card leaving a graveyard, and a permanent leaving the
  battlefield, are look-back events.
- CR 205.2a: the card types a "<type> spells" count names; CR 601.2i: a spell
  becomes cast, and is counted in `Game.spells_cast_this_turn`.
- CR 700.4: dies means "is put into a graveyard from the battlefield".
- CR 700.13: a crime - casting a spell, activating an ability, or putting a
  triggered ability on the stack that targets an opponent, a permanent,
  spell or ability an opponent controls, or a card in an opponent's
  graveyard.
- CR 702.122b: a creature crews a Vehicle when it is tapped to pay its crew
  cost.
- CR 500.8: effects can add phases, so a turn can have more than one combat
  phase.
- CR 508.1a: the attackers are declared all at once.
- CR 400.7: a card that changes zones is a new object.
- CR 107.14: paying {E} removes energy counters.
- CR 122.6 / 122.6a: counters put on a permanent, and who puts them.
- CR 606.3: loyalty abilities.
- CR 708.2: a face-down permanent.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from ...data.subtypes import canonical_subtype
from ...models.card import Type
from ...models.zone import Zone
from ...numbers import COUNT, ORDINAL, parse_count, parse_ordinal
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState, TargetRef
    from ...models.game import Game, TurnHistoryEntry
    from ..layers import Characteristics
    from ..triggers import GameEvent
    from . import ConditionContext

#: `Game.turn_counts` key for CR 603.10a's cards leaving a graveyard, per the
#: graveyard's owner.
CARDS_LEFT_GRAVEYARD = "cards_left_graveyard"
#: Each player's hand size as the turn began (`Game.untap_step`, CR 502.1,
#: the first thing a turn does), kept in `Game.turn_counts` so it rolls with
#: every other per-turn ledger - Mindstorm Crown's "if you had no cards in
#: hand at the beginning of this turn".
HAND_SIZE_AT_TURN_START = "hand_size_at_turn_start"
#: `Game.turn_counts` key for cards put into exile, per the card's owner.
CARDS_PUT_INTO_EXILE = "cards_put_into_exile"
#: `Game.turn_counts` keys for the life a player lost and gained during a
#: turn, written as that turn ends (`end_turn`) - read back only as last
#: turn's, since this turn's are `Player.life_lost_this_turn` and
#: `Game.life_gained_amount_this_turn`.
LIFE_LOST = "life_lost"
LIFE_GAINED = "life_gained"
#: `Game.turn_facts` keys.
COMMITTED_CRIME = "committed_crime"
PLAYED_NOT_FROM_HAND = "played_not_from_hand"
PLAYED_FROM_EXILE = "played_from_exile"
LOYALTY_ABILITY_ACTIVATED = "loyalty_ability_activated"
#: CR 702.185c: "a spell was warped this turn" - a spell cast for its warp
#: cost, per caster.
SPELL_WARPED = "spell_warped"


# -- recording -------------------------------------------------------------------


def record(game: "Game", event: "GameEvent") -> None:
    """Note what this family reads later off `event`, as it happens."""
    from ..triggers import ExtraTriggerEvent, TriggerEvent

    note_exile_arrivals(game)
    kind = event.event
    if kind is ExtraTriggerEvent.LEAVES_GRAVEYARD and event.player is not None:
        game.note_turn_count(CARDS_LEFT_GRAVEYARD, event.player, event.amount or 1)
    elif kind is TriggerEvent.DEALS_DAMAGE:
        _record_damage(game, event)
    elif kind is TriggerEvent.ENTERS_THE_BATTLEFIELD:
        _record_entered(game, event)
    elif kind is TriggerEvent.DIES:
        _record_departure(game, event, "to_graveyard")
    elif kind is TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND:
        _record_departure(game, event, "to_hand")
    elif kind is TriggerEvent.IS_SACRIFICED:
        _record_departure(game, event, "sacrificed")
    elif kind is TriggerEvent.ATTACKS and event.subject_id is not None:
        _record_attackers(game)
    elif kind is TriggerEvent.BLOCKS and event.subject_id is not None:
        _record_blockers(game)
    elif kind is TriggerEvent.BECOMES_TAPPED and event.during_cost_keyword == "crew":
        _record_crew(game, event)
    elif kind is ExtraTriggerEvent.ABILITY_ACTIVATED:
        _bind_crew(game, event)
        _record_activated(game, event)
    elif kind in (TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND):
        _record_played(game, event)


def _light_characteristics(
    event: "GameEvent", state: "CardState | None", controller: str | None
) -> "Characteristics":
    """The event subject's characteristics from what the event itself carries -
    its computed types and subtypes (CR 613.5, stamped when the event was
    built) - with the colors, supertypes and mana value of the object."""
    from ..layers import Characteristics

    return Characteristics(
        card_id=event.subject_id or (state.id if state is not None else UUID(int=0)),
        name=event.subject_name or (state.name if state is not None else ""),
        controller=controller,
        types=tuple(event.subject_types or (state.types if state is not None else ())),
        subtypes=tuple(event.subject_subtypes or (state.subtypes if state is not None else ())),
        supertypes=tuple(state.supertypes) if state is not None else (),
        colors=tuple(event.subject_colors or (state.colors if state is not None else ())),
        mana_value=float(state.mana_value) if state is not None else 0.0,
        is_token=bool(getattr(state, "token", False)),
    )


def _record_entered(game: "Game", event: "GameEvent") -> None:
    from ...models.game import TurnHistoryEntry

    state = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    state = state if _is_card_state(state) else None
    controller = event.subject_controller
    game.turn_history.append(
        TurnHistoryEntry(
            kind="entered",
            player=controller,
            owner=state.owner if state is not None else None,
            object_id=event.subject_id,
            characteristics=_light_characteristics(event, state, controller),
            face_down=bool(state is not None and state.face_down),
            cast_mana_spent=_cast_mana_spent(game, state),
            damage_baseline=_ledger_damage_to(game, event.subject_id),
        )
    )


def _ledger_damage_to(game: "Game", object_id: "UUID | None") -> int:
    """Everything `Game.damage_dealt_this_turn` holds for `object_id`."""
    if object_id is None:
        return 0
    return sum(
        record.amount for record in game.damage_dealt_this_turn if record.recipient_id == object_id
    )


def damage_dealt_to_object_this_turn(game: "Game", object_id: "UUID | None") -> int:
    """The damage dealt to the object `object_id` names this turn (CR 120.1),
    counted for the incarnation that last entered the battlefield: it is
    read off the ledger, which outlives a zone change, so it still answers
    for a creature that has died (CR 608.2h's last-known information). A
    card that came back this turn is a new object (CR 400.7) and does not
    inherit what its previous self was dealt."""
    total = _ledger_damage_to(game, object_id)
    for entry in reversed(game.turn_history):
        if entry.kind == "entered" and entry.object_id == object_id:
            return max(total - entry.damage_baseline, 0)
    return total


def _cast_mana_spent(game: "Game", state: "CardState | None") -> int | None:
    """The mana spent to cast the spell `state` was (CR 601.2h, CR 400.7d), or
    None when it was not cast - no record, or a copy that was never cast
    (CR 707.10)."""
    if state is None:
        return None
    record = game.cast_record_of(state)
    if record is None or record.is_copy:
        return None
    return sum(record.mana_spent.values())


def _record_departure(game: "Game", event: "GameEvent", kind: str) -> None:
    """A permanent leaving the battlefield for a graveyard (CR 700.4) or a
    hand, or being sacrificed (CR 701.21a): what it was as it last existed on
    the battlefield (CR 603.10a) - `Game._left_battlefield_characteristics`,
    taken while it was still there, when the move has already happened."""
    from ...models.game import TurnHistoryEntry

    state = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    state = state if _is_card_state(state) else None
    controller = event.subject_controller
    looked_back = (
        game._left_battlefield_characteristics.get(event.subject_id)
        if kind != "sacrificed" and event.subject_id is not None
        else None
    )
    characteristics = looked_back or _light_characteristics(event, state, controller)
    owner = state.owner if state is not None else None
    if kind == "to_hand" and event.player is not None:
        owner = event.player
    game.turn_history.append(
        TurnHistoryEntry(
            kind=kind,
            player=controller or characteristics.controller,
            owner=owner,
            object_id=event.subject_id,
            characteristics=characteristics,
        )
    )


def _current_combat(game: "Game") -> int:
    turn = game.turn
    if turn is None:
        return 0
    return game.turn_count("combat_phases", turn.active_player)


def _record_attackers(game: "Game") -> None:
    """Every creature in this combat's declaration (CR 508.1a: declared all at
    once), noted the first time any of their attack events is raised - so
    "if Tolsimir attacked this combat" is already true for a Wolf whose own
    attack event comes before Tolsimir's."""
    from ...models.game import TurnHistoryEntry

    combat = _current_combat(game)
    noted = {
        entry.object_id
        for entry in game.turn_history
        if entry.kind == "attacked" and entry.combat == combat
    }
    for attack in game.combat.attacks:
        if attack.attacker_id in noted:
            continue
        creature = game.find_by_id(attack.attacker_id)
        if not _is_card_state(creature):
            continue
        characteristics = game.characteristics_of(creature)
        game.turn_history.append(
            TurnHistoryEntry(
                kind="attacked",
                player=characteristics.controller or creature.controller,
                owner=creature.owner,
                object_id=creature.id,
                characteristics=characteristics,
                combat=combat,
            )
        )


def _record_blockers(game: "Game") -> None:
    """Every creature declared as a blocker this combat (CR 509.1g), noted
    the first time any of their `BLOCKS` events is raised - the blocking
    twin of `_record_attackers`, read by Clockwork Steed's and Daredevil
    Dragster's own "attacked or blocked this combat" (`_attacked_or_
    blocked`)."""
    from ...models.game import TurnHistoryEntry

    combat = _current_combat(game)
    noted = {
        entry.object_id
        for entry in game.turn_history
        if entry.kind == "blocked" and entry.combat == combat
    }
    for blocker_id in game.combat.blocker_ids:
        if blocker_id in noted:
            continue
        creature = game.find_by_id(blocker_id)
        if not _is_card_state(creature):
            continue
        characteristics = game.characteristics_of(creature)
        game.turn_history.append(
            TurnHistoryEntry(
                kind="blocked",
                player=characteristics.controller or creature.controller,
                owner=creature.owner,
                object_id=creature.id,
                characteristics=characteristics,
                combat=combat,
            )
        )


def _record_crew(game: "Game", event: "GameEvent") -> None:
    """CR 702.122b: this creature crews a Vehicle - tapped to pay its crew
    cost. Which Vehicle is only known once the crew ability is activated
    (`_bind_crew`)."""
    from ...models.game import TurnHistoryEntry

    state = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    state = state if _is_card_state(state) else None
    player = event.during_cost_player or event.subject_controller
    game.turn_history.append(
        TurnHistoryEntry(
            kind="crewed",
            player=player,
            object_id=event.subject_id,
            characteristics=_light_characteristics(event, state, event.subject_controller),
        )
    )


def _record_activated(game: "Game", event: "GameEvent") -> None:
    """An activated ability that is not a mana ability, with its source as it
    was - what "the first activated ability of an artifact you activate each
    turn" (`machines/cost/abilities.py`) counts. Only an artifact's activation
    is kept: artifact is the one quality that line prints, and an entry per
    activation of anything else would churn every recorded game state for a
    count nothing reads."""
    from ...models.card import Type
    from ...models.game import TurnHistoryEntry

    if Type.ARTIFACT not in (event.subject_types or ()):
        return

    state = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    state = state if _is_card_state(state) else None
    game.turn_history.append(
        TurnHistoryEntry(
            kind="activated",
            player=event.player,
            owner=state.owner if state is not None else None,
            object_id=event.subject_id,
            characteristics=_light_characteristics(event, state, event.subject_controller),
        )
    )


def _bind_crew(game: "Game", event: "GameEvent") -> None:
    if event.subject_id is None:
        return
    for index, entry in enumerate(game.turn_history):
        if entry.kind == "crewed" and entry.related_id is None and entry.player == event.player:
            game.turn_history[index] = entry.model_copy(update={"related_id": event.subject_id})


def _record_played(game: "Game", event: "GameEvent") -> None:
    """A land played or a spell cast, by the zone it came from (CR 601.2a
    moves a spell from where it is to the stack; CR 305.1 plays a land)."""
    if event.player is None or event.origin_zone is None:
        return
    if event.origin_zone is not Zone.HAND:
        game.record_turn_fact(PLAYED_NOT_FROM_HAND, event.player)
    if event.origin_zone is Zone.EXILE:
        game.record_turn_fact(PLAYED_FROM_EXILE, event.player)
    if event.subject_stamp is not None:
        # CR 702.185c: "a spell was warped this turn" means one was cast for
        # its warp cost - the spell's own `CastRecord` (CR 601.2b announced
        # the alternative cost, CR 601.2h paid it). A warped card cast later
        # from exile is cast for its mana cost, not its warp cost.
        record = game.cast_records.get(event.subject_stamp)
        if (
            record is not None
            and (record.keyword or "").lower() == "warp"
            and record.keyword_cost_paid
        ):
            game.record_turn_fact(SPELL_WARPED, event.player)


def _record_damage(game: "Game", event: "GameEvent") -> None:
    from ...models.game import DamageDealt

    source = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    source = source if _is_card_state(source) else None
    types = tuple(event.subject_types or ())
    # CR 109.2b: a spell is a card on the stack. An instant or sorcery deals
    # damage only as a spell resolving (CR 608.2), whether or not it is still
    # on the stack at that instant; any other source is one only while it is
    # on the stack itself.
    was_spell = getattr(source, "zone", None) is Zone.STACK or any(
        each in (Type.INSTANT, Type.SORCERY) for each in types
    )
    supertypes: tuple = ()
    colors: tuple = ()
    if source is not None:
        if source.zone is Zone.BATTLEFIELD:
            chars = game.characteristics_of(source)
            supertypes, colors = tuple(chars.supertypes), tuple(chars.colors)
        else:
            supertypes, colors = tuple(source.supertypes), tuple(source.colors)
    elif event.subject_card is not None:
        # A resolving spell is in no zone `find_by_id` searches: its printing
        # travels on the event.
        supertypes = tuple(event.subject_card.supertypes)
        colors = tuple(event.subject_card.colors or ())
    game.damage_dealt_this_turn.append(
        DamageDealt(
            source_id=event.subject_id,
            source_controller=event.subject_controller,
            source_types=types,
            source_subtypes=tuple(event.subject_subtypes or ()),
            source_was_spell=was_spell,
            recipient_id=event.target_id,
            recipient_player=event.player if event.target_id is None else None,
            amount=event.amount or 0,
            combat=event.combat,
            source_supertypes=supertypes,
            source_colors=colors,
            recipient_types=tuple(event.target_types or ()),
            recipient_controller=event.target_controller,
            excess=game._pending_damage_excess if event.target_id is not None else 0,
        )
    )
    if event.combat and event.target_id is None and event.player is not None:
        game.dealt_combat_damage_since_their_turn.add(event.player)


def _is_card_state(value: object) -> bool:
    from ...models.card_state import CardState

    return isinstance(value, CardState)


def _exile_key(card: "CardState") -> str:
    return f"{card.id}/{card.zone_change_stamp}"


def note_exile_arrivals(game: "Game", *, count: bool = True) -> None:
    """Count every card in exile this turn has not seen there yet as put into
    exile (CR 400.7: each move makes a new object, so the id and the zone
    change stamp together name the arrival). Called on every event and just
    before any card is lifted out of exile, so a card exiled and taken back out
    at once still counts; `count=False` only takes the residents as a
    baseline - a board staged with cards already in exile."""
    seen = game.exile_residents_seen
    for card in game.exile:
        if not _is_card_state(card):
            continue
        key = _exile_key(card)
        if key in seen:
            continue
        seen.add(key)
        if count and not getattr(card, "token", False) and card.owner is not None:
            game.note_turn_count(CARDS_PUT_INTO_EXILE, card.owner, 1)


def end_turn(game: "Game", previous_turns_taken: int, previous_active_player: str | None) -> None:
    """Close off the turn that just ended, before its ledgers roll: the life
    each player lost (CR 119.3, 120.3a) and gained that turn into the count
    ledger that becomes `turn_counts_last_turn`; the exile zone as the new
    turn's baseline; and the ending turn's active player's "since your last
    turn" combat damage cleared."""
    note_exile_arrivals(game)
    for player in game.players:
        lost = player.life_lost_tally if player.life_lost_tally_turn == previous_turns_taken else 0
        if lost:
            game.note_turn_count(LIFE_LOST, player.username, lost)
        gained = game.life_gained_amount_this_turn.get(player.username, 0)
        if gained:
            game.note_turn_count(LIFE_GAINED, player.username, gained)
    game.exile_residents_seen = {_exile_key(card) for card in game.exile if _is_card_state(card)}
    if previous_active_player is not None:
        game.dealt_combat_damage_since_their_turn.discard(previous_active_player)


def _commit_crime(game: "Game", controller: str) -> None:
    """CR 700.13's crime, both halves of what a card watching it needs: the
    turn-scoped fact an intervening "if" reads ("you've committed a crime
    this turn") and the `GameEvent` a "Whenever you commit a crime" trigger
    watches (`ExtraTriggerEvent.CRIME_COMMITTED`) - Magda, the Hoardmaster's
    and Forsaken Miner's identical condition. One event per crime-committing
    action, never per qualifying target: CR 700.13 is about the act of
    casting/activating/triggering with a qualifying target, not a count of
    how many targets qualified."""
    from ..triggers import ExtraTriggerEvent, GameEvent

    game.record_turn_fact(COMMITTED_CRIME, controller)
    game.emit(GameEvent(event=ExtraTriggerEvent.CRIME_COMMITTED, player=controller))


def record_crime(game: "Game", controller: str | None, targets: "list[TargetRef]") -> None:
    """CR 700.13: `controller` commits a crime if any of `targets` is an
    opponent, a permanent, spell or ability an opponent controls, or a card in
    an opponent's graveyard."""
    if controller is None:
        return
    for target in targets:
        if target.username is not None:
            if target.username != controller:
                _commit_crime(game, controller)
                return
            continue
        if target.card_id is None:
            continue
        found = game.find_by_id(target.card_id)
        if found is None:
            continue
        zone = getattr(found, "zone", None)
        if zone is Zone.GRAVEYARD:
            whose = getattr(found, "owner", None)
        elif zone in (Zone.BATTLEFIELD, Zone.STACK) or not _is_card_state(found):
            whose = (
                game.controller_of(found).username
                if _is_card_state(found)
                else getattr(found, "controller", None)
            )
        else:
            continue
        if whose is not None and whose != controller:
            _commit_crime(game, controller)
            return


def excess_damage(
    game: "Game", target: "CardState", amount: int, source: "CardState | None"
) -> int:
    """CR 120.10's excess damage `amount` deals to `target`, measured against
    `target` as it is now - before the damage: more than lethal damage for a
    creature (CR 120.6, less what is already marked; any nonzero combat damage
    from a deathtouch source is lethal, CR 702.2c), more than its loyalty for a
    planeswalker, more than its defense for a battle - the greatest where it
    is more than one of those."""
    from ...models.card_state import Counter
    from ..combat import Keyword, source_had_keyword

    if target.zone is Zone.BATTLEFIELD:
        chars = game.characteristics_of(target)
        types, toughness = chars.types, chars.toughness
    else:
        types, toughness = target.types, target.toughness
    candidates = [0]
    if Type.CREATURE in types and toughness is not None:
        lethal = max(toughness - target.damage, 0)
        if (
            lethal > 0
            and game._dealing_combat_damage
            and source is not None
            and source_had_keyword(source, Keyword.DEATHTOUCH, game)
        ):
            lethal = 1
        candidates.append(amount - lethal)
    if Type.PLANESWALKER in types:
        candidates.append(amount - target.counter_count(Counter.LOYALTY))
    if Type.BATTLE in types:
        candidates.append(amount - target.counter_count("defense"))
    return max(candidates)


# -- shared reading helpers ----------------------------------------------------


def _opponents(context: "ConditionContext") -> list[str]:
    return [
        player.username
        for player in context.game.players_in_game
        if player.username != context.controller
    ]


def _event_player(context: "ConditionContext") -> str | None:
    """ "that player" / "they": the player the trigger event names."""
    event = context.event
    if event is None:
        return None
    return event.player or event.subject_controller


def _players(context: "ConditionContext", who: str) -> list[str]:
    """The players a subject word names: "you", "an opponent" (any one),
    "a player" (any), "that player"/"they" (the event's)."""
    who = who.strip()
    if who == "you":
        return [context.controller]
    if who in ("an opponent", "opponents", "each opponent"):
        return _opponents(context)
    if who in ("a player", "any player"):
        return [player.username for player in context.game.players_in_game]
    if who in ("that player", "they"):
        player = _event_player(context)
        return [player] if player is not None else []
    return []


def _count(word: str | None) -> int | None:
    if word is None:
        return 1
    return parse_count(word)


_ARTICLE = re.compile(r"^(?:an?|one|another|any)\s+")
_LIST_SPLIT = re.compile(r",\s*(?:and/or\s+|or\s+|and\s+)?|\s+and/or\s+|\s+or\s+")


def _quality(phrase: str) -> "Callable[[TurnHistoryEntry], bool] | None":
    """A noun phrase naming what kind of object an entry was - "artifact or
    creature", "nonland permanents", "face-down creature", "Angel or
    Berserker", "non-Skeleton creature" - through `models/game.
    _permanent_quality` (CR 613.5's computed characteristics), with CR
    708.2's "face-down" read off the entry. None when any word is unread."""
    from ...models.game import _permanent_quality

    items = [item.strip() for item in _LIST_SPLIT.split(phrase.strip()) if item.strip()]
    tests: list[Callable[[TurnHistoryEntry], bool]] = []
    for item in items:
        item = _ARTICLE.sub("", item)
        words = item.split()
        face_down = "face-down" in words
        words = [word for word in words if word != "face-down"]
        if not words:
            return None
        characteristic = _permanent_quality(" ".join(words))
        if characteristic is None:
            return None

        def test(entry, characteristic=characteristic, face_down=face_down) -> bool:
            if face_down and not entry.face_down:
                return False
            return entry.characteristics is not None and characteristic(entry.characteristics)

        tests.append(test)
    if not tests:
        return None
    return lambda entry: any(test(entry) for test in tests)


def _entries(context: "ConditionContext", kind: str, *, last_turn: bool = False) -> list:
    game = context.game
    ledger = game.turn_history_last_turn if last_turn else game.turn_history
    return [entry for entry in ledger if entry.kind == kind]


def _subject_object(context: "ConditionContext", subject: str) -> "CardState | None":
    """The object a condition's subject names: the source itself (CR 700.7's
    "this <something>", a name it calls itself by, "he"/"she"); the object it
    is attached to ("equipped creature", "enchanted creature"); or the trigger
    event's own object ("that creature", "it" when an event is at hand)."""
    from ...models.game import _names_the_source

    source = context.source
    subject = subject.strip()
    if subject in ("equipped creature", "enchanted creature", "enchanted permanent"):
        if source is None or source.attached_to is None:
            return None
        found = context.game.find_by_id(source.attached_to)
        return found if _is_card_state(found) else None
    if subject in ("that creature", "that permanent"):
        event = context.event
        if event is None or event.subject_id is None:
            return None
        found = context.game.find_by_id(event.subject_id)
        return found if _is_card_state(found) else None
    if source is None:
        return None
    if subject == "it" or _names_the_source(subject, source):
        return source
    return None


#: A condition's subject that names one object: the source ("this creature",
#: a legend's own name, "he"/"she"), what it is attached to, or the event's own
#: object. A name is up to four words and never opens with a determiner or
#: pronoun another reader owns ("you", "a", "an", "that player").
_SUBJECT = (
    r"(?P<subject>this [a-z]+|equipped creature|enchanted creature|enchanted permanent"
    r"|that creature|that permanent|he|she|it"
    r"|(?!(?:you|a|an|another|each|no|one|two|three|that|this|they|it)\b)"
    r"[a-z][a-z',-]*(?: [a-z][a-z',-]*){0,3})"
)


# -- H1: attacks and crews -------------------------------------------------------


def _attacked(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> attacked / didn't attack this turn / this combat" (CR 508.1)."""
    target = _subject_object(context, match.group("subject"))
    if target is None:
        return False
    this_combat = match.group("when") == "combat"
    combat = _current_combat(context.game)
    attacked = any(
        entry.object_id == target.id and (not this_combat or entry.combat == combat)
        for entry in _entries(context, "attacked")
    )
    return not attacked if match.group("neg") else attacked


def _attacked_or_blocked(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> attacked or blocked this combat" (CR 508.1, CR 509.1g) -
    Clockwork Steed's and Daredevil Dragster's own end-of-combat intervening
    if. Kept apart from `_attacked`'s plain "or"-free "attacked this turn/
    combat": the generic compound splitter (`machines/conditions/__init__.
    _read_compound`) reads "X or Y" as two independent halves, which loses
    the shared subject here - "X attacked or blocked" is CR omitted-subject
    templating for "X attacked or X blocked", not "X attacked" read against
    "blocked" with no subject of its own at all."""
    target = _subject_object(context, match.group("subject"))
    if target is None:
        return False
    combat = _current_combat(context.game)
    return any(
        entry.object_id == target.id and entry.combat == combat
        for entry in (*_entries(context, "attacked"), *_entries(context, "blocked"))
    )


def _attackers_this_combat(context: "ConditionContext", controller: str | None = None) -> list:
    combat = _current_combat(context.game)
    return [
        entry
        for entry in _entries(context, "attacked")
        if entry.combat == combat and (controller is None or entry.player == controller)
    ]


def _you_attacked_with(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you attacked with exactly N [other] creatures this combat" and "... N
    or more ..." - the creatures you declared as attackers this combat (CR
    508.1a), "other" leaving the source out."""
    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    source_id = context.source.id if context.source is not None else None
    attackers = [
        entry
        for entry in _attackers_this_combat(context, context.controller)
        if not (match.group("other") and entry.object_id == source_id)
    ]
    if match.group("exactly"):
        return len(attackers) == needed
    return len(attackers) >= needed


def _you_did_not_attack(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you didn't attack [with a creature] this turn" - no attacker declared
    (CR 508.1)."""
    return not any(entry.player == context.controller for entry in _entries(context, "attacked"))


def _qualities_attacked(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a Pirate and a Vehicle attacked this combat" - each named kind among
    this combat's attackers."""
    this_combat = match.group("when") == "combat"
    attackers = _attackers_this_combat(context) if this_combat else _entries(context, "attacked")
    for part in re.split(r"\s+and\s+", match.group("list")):
        quality = _quality(part)
        if quality is None or not any(quality(entry) for entry in attackers):
            return False
    return True


def _subject_and_others_attacked(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "Kytheon and at least two other creatures attacked this combat"."""
    target = _subject_object(context, match.group("subject"))
    needed = parse_count(match.group("count"))
    if target is None or needed is None:
        return False
    attackers = _attackers_this_combat(context)
    if not any(entry.object_id == target.id for entry in attackers):
        return False
    others = [entry for entry in attackers if entry.object_id != target.id]
    return len(others) >= needed


def _creatures_attacked_count(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "three or more creatures attacked this turn" (Case of the Gateway
    Express's To solve, CR 719.3a) - every creature declared as an attacker
    this turn (CR 508.1a), by any player, each counted once."""
    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    attacked = {entry.object_id for entry in _entries(context, "attacked")}
    return len(attacked) >= needed


def _crewed(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "an Assassin crewed it this turn" (CR 702.122b)."""
    quality = _quality(match.group("quality"))
    source = context.source
    if quality is None or source is None:
        return False
    return any(
        entry.related_id == source.id and quality(entry) for entry in _entries(context, "crewed")
    )


# -- H2: zone changes ------------------------------------------------------------


def _died_under(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a [non-X] creature died under your / an opponent's control this turn"
    (CR 700.4), judged by who controlled it and what it was as it died (CR
    603.10a)."""
    quality = _quality(match.group("quality"))
    needed = _count(match.group("count"))
    if quality is None or needed is None:
        return False
    whose = _players(
        context,
        {"your": "you", "an opponent's": "an opponent", None: "a player"}[match.group("whose")],
    )
    died = [
        entry
        for entry in _entries(context, "to_graveyard")
        if entry.player in whose and quality(entry)
    ]
    return len(died) >= needed


def _put_into_graveyard_from_battlefield(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "an artifact or creature was put into a graveyard from the battlefield
    this turn", "an enchantment was put into your graveyard ..." (CR 700.4's
    move, of any permanent)."""
    quality = _quality(match.group("quality"))
    needed = _count(match.group("count"))
    if quality is None or needed is None:
        return False
    whose = match.group("whose")
    owners = (
        None
        if whose in (None, "a")
        else _players(context, "you" if whose == "your" else "an opponent")
    )
    arrivals = [
        entry
        for entry in _entries(context, "to_graveyard")
        if (owners is None or entry.owner in owners) and quality(entry)
    ]
    return len(arrivals) >= needed


def _put_into_hand_from_battlefield(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a permanent was put into your hand from the battlefield this turn" -
    whose hand is the card's owner's (CR 108.3)."""
    quality = _quality(match.group("quality"))
    needed = _count(match.group("count"))
    if quality is None or needed is None:
        return False
    owners = _players(context, "you" if match.group("whose") == "your" else "a player")
    returned = [
        entry for entry in _entries(context, "to_hand") if entry.owner in owners and quality(entry)
    ]
    return len(returned) >= needed


def _cards_put_into_exile(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "one or more cards were put into exile this turn" (CR 400.7)."""
    needed = _count(match.group("count"))
    if needed is None:
        return False
    note_exile_arrivals(context.game)
    total = sum(context.game.turn_counts.get(CARDS_PUT_INTO_EXILE, {}).values())
    return total >= needed


def _cards_left_your_graveyard(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "[N or more cards | a card] left your graveyard this turn" (CR 603.10a),
    counted as each departure's event was raised."""
    needed = parse_count(match.group("count")) if match.group("count") else 1
    if needed is None:
        return False
    return context.game.turn_count(CARDS_LEFT_GRAVEYARD, context.controller) >= needed


# -- EC7: tokens created, graveyard arrivals from anywhere, fights ---------------


def _created_a_token(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you created a token this turn" (CR 111.2, CR 701.7a) - Bennie Bracks,
    Zoologist's own end-step intervening if; Idol of Oblivion prints the
    identical condition as a CR 602.5b activation restriction instead, so the
    same clause is proven read on both rules paths this package's readers
    are shared by (`machines/conditions/__init__.py`'s own docstring).
    `models.token._note_token_creation` already notes every token-creation
    event (CR 701.7b) per player per turn; no card in Magic's history prints
    this template on a Modern/Pioneer/Standard-legal card, so Idol of
    Oblivion - Legacy/Vintage/Commander-legal only - stands in for the
    Scryfall-searched, format-legal second printing this package's other
    readers are proven on."""
    from ...models.token import TOKEN_CREATION_FACT

    return context.game.turn_count(TOKEN_CREATION_FACT, context.controller) > 0


def _card_type_quality(word: str) -> "Callable[[tuple[Type, ...]], bool] | None":
    """A `GraveyardArrival.card_types` quality word - a card type (CR 110.4),
    "permanent" (CR 110.4a's six-type union), or a "non" negation of either -
    the same one-word grammar `models.game._card_quality` reads off a live
    `CardState`, narrowed to types alone: a `GraveyardArrival` never keeps
    subtypes, because an arrival that skipped the battlefield (a discard, a
    mill, a countered spell) has none computed to keep (`GraveyardArrival.
    card_types`'s own docstring). None when the word is not a type or
    "permanent"."""
    from ...models.game import _PERMANENT_TYPES, _card_type_named

    lowered = word.strip().lower()
    if lowered == "permanent":
        return lambda types: bool(_PERMANENT_TYPES.intersection(types))
    if lowered.startswith("non") and len(lowered) > 4:
        inner = _card_type_quality(lowered.removeprefix("non").lstrip("-"))
        if inner is None:
            return None
        return lambda types: not inner(types)
    card_type = _card_type_named(lowered)
    if card_type is None:
        return None
    return lambda types: card_type in types


def _card_put_into_graveyard_from_anywhere(
    context: "ConditionContext", match: re.Match[str]
) -> bool:
    """ "a <type> card was put into your graveyard from anywhere this turn"
    (CR 700.11's own "from anywhere", the same look-back `Game.descended`
    already reads for the unqualified "permanent card" template) - Raphael,
    Fiendish Savior's own end-step intervening if, generalized from
    "creature" to any card type rather than hardcoded to it. Macabre
    Reconstruction prints the identical condition as a CR 601.2f cost
    reduction, read through the same `Game.condition_holds` this package's
    readers all share - proof the clause reads on a second rules path, not
    only a second card, since no other quality word (only "creature" and the
    unqualified "permanent"/"card" `descended` already owns) is printed on
    any Magic card at all."""
    quality = _card_type_quality(match.group("quality"))
    needed = _count(match.group("count"))
    if quality is None or needed is None:
        return False
    whose = match.group("whose")
    owners = _players(context, "you" if whose == "your" else "an opponent")
    matches = sum(
        1
        for arrival in context.game.graveyard_arrivals_this_turn
        if arrival.player in owners and quality(arrival.card_types)
    )
    return matches >= needed


#: `Game.turn_history` `kind` for CR 701.14's fight - both participants,
#: recorded by `record_fight` directly from `machines/effects._fight` rather
#: than through `record`'s event dispatch, the same way `record_crime`/
#: `excess_damage` are: CR 701.14a's damage is dealt through the ordinary
#: `DEALS_DAMAGE` event, which carries no "this was a fight" marker of its
#: own for `record` to key off.
FOUGHT = "fought"


def record_fight(game: "Game", a: "CardState", b: "CardState") -> None:
    """Note that `a` and `b` fought each other this turn (CR 701.14a) - Boxing
    Ring's own "Activate only if you control a creature that fought this
    turn", read generically for any quality by `machines/conditions/board.
    py`'s "that fought this turn" quality suffix, which shares the ordinary
    `quality()`/`_controls` grammar every other suffix already does."""
    from ...models.game import TurnHistoryEntry

    for creature in (a, b):
        if creature.zone is not Zone.BATTLEFIELD:
            continue
        characteristics = game.characteristics_of(creature)
        game.turn_history.append(
            TurnHistoryEntry(
                kind=FOUGHT,
                player=characteristics.controller or creature.controller,
                owner=creature.owner,
                object_id=creature.id,
                characteristics=characteristics,
            )
        )


def fought_this_turn(game: "Game", object_id: UUID) -> bool:
    """Whether the permanent `object_id` fought this turn (CR 701.14a) -
    `record_fight`'s own ledger, read by `machines/conditions/board.py`'s
    "that fought this turn" quality suffix without that module needing to
    know `Game.turn_history`'s own shape."""
    return any(entry.kind == FOUGHT and entry.object_id == object_id for entry in game.turn_history)


# -- H3: permanents entering ------------------------------------------------------


def _entered(
    context: "ConditionContext",
    quality_phrase: str,
    players: list[str],
    *,
    last_turn: bool,
    exclude: UUID | None,
) -> list | None:
    quality = _quality(quality_phrase)
    if quality is None:
        return None
    return [
        entry
        for entry in _entries(context, "entered", last_turn=last_turn)
        if entry.player in players and entry.object_id != exclude and quality(entry)
    ]


def _had_enter(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you had a land enter the battlefield under your control this turn",
    "you had an Angel or Berserker enter ...", "that player had another land
    enter ... under their control this turn", "... last turn" - "another"
    leaving out the source, or the trigger event's own permanent when the
    subject is the event's player."""
    who = match.group("who")
    players = _players(context, who)
    exclude = None
    if match.group("another"):
        if who == "you" and context.source is not None:
            exclude = context.source.id
        elif context.event is not None:
            exclude = context.event.subject_id
    found = _entered(
        context,
        match.group("quality"),
        players,
        last_turn=match.group("when") == "last",
        exclude=exclude,
    )
    return bool(found)


def _counted_entered(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "two or more nonland permanents entered the battlefield under your
    control this turn", "a face-down creature entered ...", "another creature
    entered ..." (CR 110.4, CR 708.2)."""
    needed = _count(match.group("count"))
    if needed is None:
        return False
    exclude = context.source.id if match.group("another") and context.source is not None else None
    found = _entered(
        context,
        match.group("quality"),
        [context.controller],
        last_turn=match.group("when") == "last",
        exclude=exclude,
    )
    return found is not None and len(found) >= needed


def _this_or_another_entered(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this artifact or another artifact entered the battlefield under your
    control this turn" - any of that kind, the source included."""
    if match.group("first") != match.group("second"):
        return False
    found = _entered(
        context, match.group("second"), [context.controller], last_turn=False, exclude=None
    )
    return bool(found)


def _subject_entered(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> entered / didn't enter [the battlefield] this turn" - off
    `CardState.turn_entered`, the stamp `Game.enter_the_battlefield` writes."""
    target = _subject_object(context, match.group("subject"))
    if target is None:
        return False
    entered = context.game._entered_this_turn(target)
    return not entered if match.group("neg") else entered


# -- H4: life, damage, energy ------------------------------------------------------


def _life_changed(context: "ConditionContext", player: str, what: str, *, last_turn: bool) -> int:
    game = context.game
    if last_turn:
        return game.turn_count(LIFE_LOST if what == "lost" else LIFE_GAINED, player, last_turn=True)
    if what == "lost":
        found = next((each for each in game.players if each.username == player), None)
        return found.life_lost_this_turn if found is not None else 0
    return game.life_gained_amount_this_turn.get(player, 0)


def _life_this_turn(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<who> gained / lost [N or more] life this turn / last turn", "you
    gained and lost life", "you gained or lost life", "you didn't lose life"
    (CR 119.3; damage is life loss too, CR 120.3a)."""
    needed = _count(match.group("count"))
    if needed is None:
        return False
    last_turn = match.group("when") == "last"
    verbs = re.split(r"\s+(and|or)\s+", match.group("verbs"))
    joiner = verbs[1] if len(verbs) > 1 else "and"
    changes = [verbs[0]] + ([verbs[2]] if len(verbs) > 2 else [])
    for player in _players(context, match.group("who")):
        results = [
            _life_changed(
                context, player, "lost" if "los" in verb else "gained", last_turn=last_turn
            )
            >= needed
            for verb in changes
        ]
        if (all(results) if joiner == "and" else any(results)) is True:
            return True
    return False


def _did_not_lose_life(context: "ConditionContext", match: re.Match[str]) -> bool:
    last_turn = match.group("when") == "last"
    return all(
        _life_changed(context, player, "lost", last_turn=last_turn) == 0
        for player in _players(context, match.group("who"))
    )


def _source_quality(phrase: str) -> "Callable[[object], bool] | None":
    """A damage source's description - "a legendary creature", "red sources",
    "a Giant, Wizard, or spell" - as a test on a `DamageDealt` record: a CR
    109.2b spell, a color (CR 105.1), a supertype, a card type (CR 205.2a) or
    a subtype, every word of each item read."""
    from ...models.card import Supertype
    from ...models.game import _COLOR_WORDS

    items = [item.strip() for item in _LIST_SPLIT.split(phrase.strip()) if item.strip()]
    item_tests = []
    for item in items:
        words = _ARTICLE.sub("", item).split()
        word_tests = []
        for word in words:
            singular = word.removesuffix("s") if word not in ("sources",) else "source"
            if word in ("source", "sources"):
                continue
            if word in ("spell", "spells"):
                word_tests.append(lambda record: record.source_was_spell)
                continue
            color = _COLOR_WORDS.get(word)
            if color is not None:
                word_tests.append(lambda record, color=color: color in record.source_colors)
                continue
            supertype = next((each for each in Supertype if each.value == word), None)
            if supertype is not None:
                word_tests.append(
                    lambda record, supertype=supertype: supertype in record.source_supertypes
                )
                continue
            card_type = next((each for each in Type if each.value == singular), None)
            if card_type is not None:
                word_tests.append(
                    lambda record, card_type=card_type: card_type in record.source_types
                )
                continue
            subtype = canonical_subtype(word)
            if subtype is not None:
                word_tests.append(
                    lambda record, subtype=subtype: (
                        subtype in {each.lower() for each in record.source_subtypes}
                    )
                )
                continue
            return None
        item_tests.append(
            lambda record, word_tests=word_tests: all(test(record) for test in word_tests)
        )
    if not item_tests:
        return None
    return lambda record: any(test(record) for test in item_tests)


def _kind_matches(record, kind: str | None) -> bool:
    if kind == "combat":
        return record.combat
    if kind == "noncombat":
        return not record.combat
    return True


#: The shared tail of every "dealt combat damage" turn-history clause, once
#: the subject and verb ("<who> was dealt" / "controlled by a player who was
#: dealt" / "whose controller was dealt") have been stripped off by whichever
#: family reads this shape: an amount (CR 120.2a/120.2b), the combat/noncombat
#: kind, and an optional source - a quality plus a count of *distinct*
#: sources of that quality (Admiral Beckett Brass's "by three or more
#: Pirates" - CR 510.2's combat damage is dealt simultaneously, so a combat
#: with three Pirates attacking unblocked deals it in one instant, but the
#: count is of sources, not of that instant's total damage), or a specific
#: object (CR 201.5/CR 700.7's self-reference, already rewritten to "this
#: `<noun>`" by `self_normalized_effect_text` ahead of every parser that
#: reaches this - Hope of Ghirapur's and Steel Hellkite's own "this
#: creature"/"this permanent"). Exported as `dealt_damage_clause_test` for
#: `machines/targeting.py`'s "target player who ..." and "controlled by a
#: player who ..." and `machines/effects.py`'s "whose controller ..." -
#: Oracle prints the identical tail after all three subjects.
_DEALT_DAMAGE_TAIL_RE = re.compile(
    rf"(?:was|were|has been|have been) dealt (?:(?P<count>{COUNT}) or more )?"
    r"(?P<kind>combat |noncombat )?damage"
    rf"(?: by (?:(?P<by_count>{COUNT}) or more )?(?P<by>[a-z ,'-]+?))? this turn"
)

#: A self-reference already rewritten to CR 700.7's "this `<noun>`" form -
#: see `_DEALT_DAMAGE_TAIL_RE`'s own docstring for why no literal card name
#: ever reaches here.
_THIS_SELF_RE = re.compile(r"this [a-z]+")


def dealt_damage_clause_test(
    tail: str,
) -> "Callable[[Game, str | UUID, CardState | None], bool] | None":
    """`_DEALT_DAMAGE_TAIL_RE`'s shape read into a `(game, player, source) ->
    bool` test, or `None` when `tail` is not this shape or names a source
    phrase this cannot read.

    `source` is only consulted for a self-reference "by" phrase (CR 700.7) -
    the object the printed ability is on, resolved by whichever caller has
    one to give (a turn-history condition's own `context.source`, or a
    target/filter reader's own ability source) - so parsing never needs one
    to validate a quality-only "by" phrase (Admiral Beckett Brass's "by three
    or more Pirates" reads the same with `source=None`, which is what a
    parser validating the shape ahead of any game existing has to pass)."""
    match = _DEALT_DAMAGE_TAIL_RE.fullmatch(tail.strip().lower())
    if match is None:
        return None
    needed = _count(match.group("count"))
    if needed is None:
        return None
    kind = (match.group("kind") or "").strip() or None
    by_phrase = match.group("by")
    self_reference = False
    quality_test = None
    by_count = None
    if by_phrase:
        if _THIS_SELF_RE.fullmatch(by_phrase.strip()):
            self_reference = True
        else:
            quality_test = _source_quality(by_phrase)
            if quality_test is None:
                return None
        if match.group("by_count"):
            by_count = parse_count(match.group("by_count"))
            if by_count is None:
                return None

    def test(game: "Game", player: "str | UUID", source: "CardState | None" = None) -> bool:
        """`player` is a username, or a permanent's id for
        `object_dealt_damage_clause_test`."""

        def matches(record: object) -> bool:
            if not _kind_matches(record, kind):
                return False
            if self_reference:
                return source is not None and record.source_id == source.id
            return quality_test is None or quality_test(record)

        records = [
            record
            for record in game.damage_dealt_this_turn
            if (record.recipient_player == player or record.recipient_id == player)
            and matches(record)
        ]
        if by_count is not None:
            return len({record.source_id for record in records}) >= by_count
        return sum(record.amount for record in records) >= needed

    return test


def object_dealt_damage_clause_test(
    tail: str,
) -> "Callable[[Game, CardState, CardState | None], bool] | None":
    """`dealt_damage_clause_test`'s shape about a permanent rather than a
    player - Goka the Unjust's and Initiate of Blood's "target creature that
    was dealt damage this turn" (CR 120.1's damage events, read off
    `Game.damage_dealt_this_turn`'s `recipient_id`)."""
    test = dealt_damage_clause_test(tail)
    if test is None:
        return None

    def object_test(game: "Game", target: "CardState", source: "CardState | None" = None) -> bool:
        return test(game, target.id, source)

    return object_test


def _player_dealt_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<who> was dealt [N or more] [combat|noncombat] damage [by [M or
    more] <quality-or-self>] this turn" (CR 120.2a/120.2b) - the tail shared
    with `machines/targeting.py`'s and `machines/effects.py`'s own readers,
    through `dealt_damage_clause_test`."""
    test = dealt_damage_clause_test(match.group("tail"))
    if test is None:
        return False
    return any(
        test(context.game, player, context.source)
        for player in _players(context, match.group("who"))
    )


def _sources_dealt_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "red sources you controlled dealt 4 or more noncombat damage this turn"
    - the damage those sources dealt, to anything, while under your control."""
    needed = _count(match.group("count"))
    source_test = _source_quality(match.group("sources"))
    if needed is None or source_test is None:
        return False
    kind = (match.group("kind") or "").strip() or None
    total = sum(
        record.amount
        for record in context.game.damage_dealt_this_turn
        if record.source_controller == context.controller
        and _kind_matches(record, kind)
        and source_test(record)
    )
    return total >= needed


def _damage_dealt_to_subject(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "4 or more damage was dealt to it this turn" - the damage the source
    (or the object the subject names) was dealt."""
    needed = _count(match.group("count"))
    target = _subject_object(context, match.group("subject"))
    if needed is None or target is None:
        return False
    total = sum(
        record.amount
        for record in context.game.damage_dealt_this_turn
        if record.recipient_id == target.id
    )
    return total >= needed


def _recipient_matches(context: "ConditionContext", record, recipient: str) -> bool:
    recipient = recipient.strip()
    if recipient in ("a player", "any player"):
        return record.recipient_player is not None
    if recipient in ("an opponent", "each opponent"):
        return record.recipient_player in _opponents(context)
    if recipient == "you":
        return record.recipient_player == context.controller
    if recipient in ("that player", "them"):
        return record.recipient_player is not None and record.recipient_player == _event_player(
            context
        )
    card_type = next(
        (
            each
            for each in Type
            if f"a {each.value}" == recipient or f"an {each.value}" == recipient
        ),
        None,
    )
    if card_type is not None:
        return record.recipient_id is not None and card_type in record.recipient_types
    return False


def _subject_dealt_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this creature dealt damage to an opponent this turn", "equipped
    creature didn't deal combat damage to a creature this turn", "it has
    dealt 10 or more damage to that player this turn" (CR 120.1: the object
    that deals damage is its source)."""
    target = _subject_object(context, match.group("subject"))
    needed = _count(match.group("count"))
    if target is None or needed is None:
        return False
    kind = (match.group("kind") or "").strip() or None
    total = sum(
        record.amount
        for record in context.game.damage_dealt_this_turn
        if record.source_id == target.id
        and _kind_matches(record, kind)
        and _recipient_matches(context, record, match.group("to"))
    )
    dealt = total >= needed
    return not dealt if match.group("neg") else dealt


def _excess_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a creature or planeswalker an opponent controlled was dealt excess
    damage this turn" (CR 120.10)."""
    wanted: list[Type] = []
    for item in _LIST_SPLIT.split(match.group("quality")):
        word = _ARTICLE.sub("", item.strip())
        if not word:
            continue
        card_type = next((each for each in Type if each.value == word.removesuffix("s")), None)
        if card_type is None:
            return False
        wanted.append(card_type)
    controllers = _players(context, match.group("who"))
    return any(
        record.excess > 0
        and record.recipient_controller in controllers
        and any(card_type in record.recipient_types for card_type in wanted)
        for record in context.game.damage_dealt_this_turn
    )


def _not_dealt_combat_damage_since_last_turn(
    context: "ConditionContext", match: re.Match[str]
) -> bool:
    """ "you haven't been dealt combat damage since your last turn" - since
    your most recent turn ended (`Game.dealt_combat_damage_since_their_
    turn`)."""
    return context.controller not in context.game.dealt_combat_damage_since_their_turn


def _energy_paid(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've paid or lost N or more {E} this turn" (CR 107.14)."""
    from ...models.game import ENERGY_PAID_OR_LOST

    needed = _count(match.group("count"))
    if needed is None:
        return False
    return context.game.turn_count(ENERGY_PAID_OR_LOST, context.controller) >= needed


# -- H5: what a player did ----------------------------------------------------------


def _sacrificed(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've sacrificed an artifact this turn", "you sacrificed three or
    more Clues this turn" (CR 701.21a)."""
    quality = _quality(match.group("quality"))
    needed = _count(match.group("count"))
    if quality is None or needed is None:
        return False
    sacrificed = [
        entry
        for entry in _entries(context, "sacrificed")
        if entry.player == context.controller and quality(entry)
    ]
    return len(sacrificed) >= needed


def _discarded(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<who> discarded [N or more cards | a card] this turn" (CR 701.9a),
    off `Game.cards_discarded_this_turn`."""
    needed = _count(match.group("count"))
    if needed is None:
        return False
    counts = context.game.cards_discarded_this_turn
    return any(counts.get(player, 0) >= needed for player in _players(context, match.group("who")))


def _drew(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you drew two or more cards this turn" (CR 121.2), "you've drawn more
    than one card this turn" (Proft's Eidetic Memory's own intervening if) -
    off `Game.cards_drawn_this_turn`."""
    more_than = match.group("more_than")
    threshold = _count(more_than) if more_than is not None else _count(match.group("count"))
    if threshold is None:
        return False
    needed = threshold + 1 if more_than is not None else threshold
    counts = context.game.cards_drawn_this_turn
    return any(counts.get(player, 0) >= needed for player in _players(context, match.group("who")))


def _spell_quality(phrase: str | None) -> "Callable[[CardState], bool] | None":
    """A spell's quality - "instant or sorcery", "creature", "noncreature" -
    as a test on a cast spell (CR 205.2a), every item read."""
    from ...models.game import _COLOR_WORDS, _card_quality

    if phrase is None or not phrase.strip():
        return lambda state: True
    items = [_ARTICLE.sub("", item.strip()) for item in _LIST_SPLIT.split(phrase.strip())]
    tests: list[Callable[[CardState], bool]] = []
    for item in items:
        if not item:
            continue
        word_tests: list[Callable[[CardState], bool]] = []
        for word in item.split():
            color = _COLOR_WORDS.get(word)
            if color is not None:
                word_tests.append(lambda state, color=color: color in state.colors)
                continue
            quality = _card_quality(word)
            if quality is None:
                return None
            word_tests.append(quality)
        tests.append(lambda state, word_tests=word_tests: all(test(state) for test in word_tests))
    if not tests:
        return None
    return lambda state: any(test(state) for test in tests)


def _cast_a_spell(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've cast an instant or sorcery spell this turn", "that player
    didn't cast a creature spell this turn", "you've cast another instant or
    sorcery spell this turn" (CR 601.2i).

    "another" (Burrog Barrage's own resolution-time "if you've cast another
    instant or sorcery spell this turn") excludes the clause's own source by
    id (CR 201.5's "just that particular object") - `Game.spells_cast_this_
    turn` already carries the resolving spell itself, cast before its own
    effect runs, so without this a spell asking "another" this way would
    count its own cast as satisfying it. A clause with no `source` in
    context (nothing to exclude) reads "another" the same as a bare "a"."""
    quality = _spell_quality(match.group("quality"))
    if quality is None:
        return False
    exclude_id = (
        context.source.id
        if (match.group("quant") or "").lower() == "another" and context.source is not None
        else None
    )
    cast = any(
        quality(state)
        for player in _players(context, match.group("who"))
        for state in context.game.spells_cast_this_turn.get(player, [])
        if exclude_id is None or state.id != exclude_id
    )
    return not cast if match.group("neg") else cast


def _cast_mana_value(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've cast a spell with mana value 4 or greater this turn" (CR
    202.3)."""
    threshold = parse_count(match.group("count"))
    if threshold is None:
        return False
    greater = match.group("cmp") in ("greater", "more")
    for state in context.game.spells_cast_this_turn.get(context.controller, []):
        value = state.mana_value
        if (value >= threshold) if greater else (value <= threshold):
            return True
    return False


def _nth_spell(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it was the second spell you cast this turn" - the source's own
    position among the spells you cast this turn (CR 601.2i), the permanent a
    spell became keeping that spell's id."""
    ordinal = parse_ordinal(match.group("ordinal"))
    source = context.source
    if ordinal is None or source is None:
        return False
    cast = context.game.spells_cast_this_turn.get(context.controller, [])
    position = next(
        (index for index, state in enumerate(cast, start=1) if state.id == source.id), None
    )
    return position == ordinal


def _counter_records(context: "ConditionContext") -> list:
    return list(context.game.counters_put_this_turn)


def _kind_of_counter(word: str | None) -> str | None:
    if word is None:
        return None
    word = word.strip()
    return word or None


def _first_time_counters(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's the first time [+1/+1] counters have been put on that
    <permanent> this turn" (CR 122.6) - whether the placement the trigger
    event reports was the first on that object this turn: the earliest
    placement on it is that event's."""
    event = context.event
    if event is None or event.subject_id is None:
        return False
    kind = _kind_of_counter(match.group("kind"))
    found = context.game.find_by_id(event.subject_id)
    stamp = found.zone_change_stamp if _is_card_state(found) else None
    placements = [
        (index, record)
        for index, record in enumerate(_counter_records(context))
        if record.card_id == event.subject_id
        and (stamp is None or record.zone_change_stamp in (None, stamp))
        and (kind is None or record.kind == kind)
    ]
    if not placements:
        return False
    first_index, first = placements[0]
    if event.counters_put_index is not None:
        # The event names its own placement: first exactly when it is the
        # earliest one on that object this turn.
        return first_index == event.counters_put_index
    return (
        (event.counter_kind is None or first.kind == event.counter_kind)
        and (event.amount is None or first.amount == event.amount)
        and (event.player is None or first.putter == event.player)
    )


def _counter_put_on_yours(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a +1/+1 counter was put on a permanent under your control this turn"
    - who controlled it as the counter landed (CR 122.6)."""
    kind = _kind_of_counter(match.group("kind"))
    wanted = next((each for each in Type if each.value == match.group("noun")), None)
    return any(
        record.controller == context.controller
        and (kind is None or record.kind == kind)
        and (wanted is None or wanted in record.types)
        for record in _counter_records(context)
    )


def _you_put_a_counter(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you put a counter on this creature this turn", "you put a counter on a
    creature this turn" - counted by who put it (CR 122.6a)."""
    kind = _kind_of_counter(match.group("kind"))
    on = match.group("on")
    source = context.source
    for record in _counter_records(context):
        if record.putter != context.controller or (kind is not None and record.kind != kind):
            continue
        if on.startswith("this "):
            if source is not None and record.card_id == source.id:
                return True
            continue
        noun = _ARTICLE.sub("", on)
        wanted = next((each for each in Type if each.value == noun), None)
        if noun == "permanent" or (wanted is not None and wanted in record.types):
            return True
    return False


def _committed_crime(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've committed a crime this turn" (CR 700.13)."""
    return context.game.turn_fact_holds(COMMITTED_CRIME, context.controller)


def _played_not_from_hand(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've played a land or cast a spell this turn from anywhere other
    than your hand"."""
    return context.game.turn_fact_holds(PLAYED_NOT_FROM_HAND, context.controller)


def _played_from_exile(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you [didn't] play[ed] a card from exile this turn" - a land played or
    a spell cast from exile."""
    played = context.game.turn_fact_holds(PLAYED_FROM_EXILE, context.controller)
    return not played if match.group("neg") else played


def _loyalty_ability(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you [didn't] activate[d] a loyalty ability [of a planeswalker] this
    turn" (CR 606.3)."""
    activated = context.game.turn_fact_holds(LOYALTY_ABILITY_ACTIVATED, context.controller)
    return not activated if match.group("neg") else activated


def _source_you_controlled_dealt_damage(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a Giant, Wizard, or spell you controlled dealt damage to it this turn"
    (Aegar, the Freezing Flame): some damage this turn to "it" - the trigger
    event's own subject - came from a source that, as it dealt the damage,
    was under your control and matched any item of the list. A list item
    this does not read makes the whole clause false rather than guessed."""
    source_test = _source_quality(match.group("list"))
    event = context.event
    if source_test is None or event is None:
        return False
    recipient = event.target_id if event.target_id is not None else event.subject_id
    if recipient is None:
        return False
    return any(
        record.recipient_id == recipient
        and record.source_controller == context.controller
        and source_test(record)
        for record in context.game.damage_dealt_this_turn
    )


def _spells_of_types_cast(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've cast N or more <type list> spells this turn" (Urabrask's
    "three or more instant and/or sorcery spells"): each spell counted once
    if it has any of the listed card types (CR 205.2a), off
    `Game.spells_cast_this_turn` (CR 601.2i). A type word this does not read
    makes the clause false rather than guessed."""
    needed = parse_count(match.group("count"))
    if needed is None:
        return False
    wanted: set[Type] = set()
    for word in re.split(r",|\band/or\b|\band\b|\bor\b", match.group("types")):
        word = word.strip()
        if not word:
            continue
        card_type = next((each for each in Type if each.value == word.removesuffix("s")), None)
        if card_type is None:
            return False
        wanted.add(card_type)
    if not wanted:
        return False
    cast = context.game.spells_cast_this_turn.get(context.controller, [])
    return (
        sum(1 for state in cast if wanted & set(state.types_as_a_spell(state.card.types))) >= needed
    )


def _left_the_battlefield(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a nonland permanent left the battlefield this turn" (Void, an ability
    word, CR 207.2c): any permanent of the quality, whoever controlled it and
    wherever it went, as it last existed on the battlefield (CR 603.10a) -
    `Game.turn_history`'s "left_battlefield" entries, one per departure. An
    unread quality makes the clause false rather than guessed."""
    quality = _quality(match.group("quality"))
    needed = parse_count(match.group("count")) if match.group("count") else 1
    if quality is None or needed is None:
        return False
    return sum(1 for entry in _entries(context, "left_battlefield") if quality(entry)) >= needed


def _revolt(context: "ConditionContext", match: re.Match[str]) -> bool:
    """Revolt (an ability word, CR 207.2c): "a permanent left the battlefield
    under your control this turn" / "a permanent you controlled left the
    battlefield this turn" - `Game.revolt_active_for`'s running count, by the
    controller the permanent had as it left, the same fact a revolt
    intervening "if" and a Disappear "enters with" already read (Aether
    Revolt's "As long as ..." static)."""
    return context.game.revolt_active_for(context.controller)


def _spell_warped(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a spell was warped this turn" - CR 702.185c: "This means that a spell
    was cast for its warp cost this turn", by anyone (`SPELL_WARPED`)."""
    return bool(context.game.turn_facts.get(SPELL_WARPED))


def _cast_both(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've cast both a creature spell and a noncreature spell this turn"
    (Eshki Dragonclaw, Fae Offering): two different spells cast this turn
    (CR 601.2i, `Game.spells_cast_this_turn`), one of each quality (CR
    205.2a's card types as a spell). An unread quality makes it false."""
    first = _spell_quality(match.group("first"))
    second = _spell_quality(match.group("second"))
    if first is None or second is None:
        return False
    cast = [
        state
        for player in _players(context, match.group("who"))
        for state in context.game.spells_cast_this_turn.get(player, [])
    ]
    return any(
        first(one) and second(other)
        for index, one in enumerate(cast)
        for other_index, other in enumerate(cast)
        if index != other_index
    )


def _them_entered(context: "ConditionContext") -> list["TurnHistoryEntry"] | None:
    """The "entered" entries of every permanent "them" names for a "one or
    more ... enter" trigger (CR 603.6a, `GameEvent.entered_together`): the
    event's own subject, and each other member its trigger condition is true
    of (CR 603.2) - a member that has left since is kept, its facts were
    fixed as it entered. None without an event to read."""
    from ...models.card_state import CardState
    from ..abilities import TriggeredAbility
    from ..triggers import condition_matches

    event = context.event
    if event is None or event.subject_id is None:
        return None
    game = context.game
    ability = context.ability
    pairs = event.entered_together or ((event.subject_id, event.origin_zone),)
    entered = _entries(context, "entered")
    found: list[TurnHistoryEntry] = []
    for member_id, origin in pairs:
        member = game.find_by_id(member_id)
        if (
            member_id != event.subject_id
            and isinstance(member, CardState)
            and member.zone is Zone.BATTLEFIELD
            and isinstance(ability, TriggeredAbility)
            and context.source is not None
        ):
            member_event = game._enters_event(member).model_copy(update={"origin_zone": origin})
            if not condition_matches(
                game, ability, context.source, context.controller, member_event
            ):
                continue
        entries = [entry for entry in entered if entry.object_id == member_id]
        if entries:
            found.append(entries[-1])
    return found


def _none_of_them_cast(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "none of them were cast" - not one of the permanents that entered was
    cast (CR 601.2)."""
    entries = _them_entered(context)
    if entries is None:
        return False
    return all(entry.cast_mana_spent is None for entry in entries)


def _no_mana_spent_to_cast_them(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "no mana was spent to cast them" (CR 601.2h): of the permanents that
    entered, none that was cast had any mana spent on it."""
    entries = _them_entered(context)
    if entries is None:
        return False
    return all(not entry.cast_mana_spent for entry in entries)


# -- the readers ---------------------------------------------------------------------

_WHO = r"(?P<who>you|an opponent|a player|that player|they)"
_WHEN = r"(?P<when>this|last) turn"
_N_OR_MORE = rf"(?:(?P<count>{COUNT}) or more )?"
_QUALITY = r"(?P<quality>[a-z][a-z ,/'-]*?)"
_KIND = r"(?P<kind>(?:[+-]\d+/[+-]\d+|[a-z]+) )?"

READERS: tuple[ConditionReader, ...] = (
    # H1
    ConditionReader(
        re.compile(rf"{_SUBJECT} (?:(?P<neg>didn't attack)|attacked) this (?P<when>turn|combat)"),
        _attacked,
    ),
    ConditionReader(
        re.compile(rf"{_SUBJECT} attacked or blocked this combat"),
        _attacked_or_blocked,
    ),
    ConditionReader(
        re.compile(
            rf"you attacked with (?P<exactly>exactly )?(?P<count>{COUNT}) (?:or more )?"
            r"(?P<other>other )?creatures? this combat"
        ),
        _you_attacked_with,
    ),
    ConditionReader(
        re.compile(r"you didn't attack(?: with (?:a|any) creatures?)? this turn"),
        _you_did_not_attack,
    ),
    ConditionReader(
        re.compile(rf"(?P<count>{COUNT}) or more creatures attacked this turn"),
        _creatures_attacked_count,
    ),
    ConditionReader(
        re.compile(
            r"(?P<list>an? [a-z-]+(?: and an? [a-z-]+)+) attacked this (?P<when>turn|combat)"
        ),
        _qualities_attacked,
    ),
    ConditionReader(
        re.compile(
            rf"{_SUBJECT} and at least (?P<count>{COUNT}) other creatures attacked this combat"
        ),
        _subject_and_others_attacked,
    ),
    ConditionReader(
        re.compile(rf"an? {_QUALITY} crewed (?:it|this vehicle) this turn"),
        _crewed,
    ),
    # H2
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |an? ){_QUALITY} died "
            r"(?:under (?P<whose>your|an opponent's) control )?this turn"
        ),
        _died_under,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |an? ){_QUALITY} (?:was|were) put into "
            r"(?P<whose>a|your|an opponent's) graveyards? from the battlefield this turn"
        ),
        _put_into_graveyard_from_battlefield,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |an? ){_QUALITY} (?:was|were) put into "
            r"(?P<whose>your|a player's) hand from the battlefield this turn"
        ),
        _put_into_hand_from_battlefield,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more cards|one or more cards|a card) (?:was|were) put "
            r"into exile this turn"
        ),
        _cards_put_into_exile,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more cards|(?:a|one) card) left your graveyard this turn"
        ),
        _cards_left_your_graveyard,
    ),
    # H3
    ConditionReader(
        re.compile(
            rf"{_WHO} had (?P<another>another )?(?:an? )?{_QUALITY} enter the battlefield "
            rf"under (?:your|their) control {_WHEN}"
        ),
        _had_enter,
    ),
    ConditionReader(
        re.compile(
            r"this (?P<first>[a-z]+) or another (?P<second>[a-z]+) entered the battlefield "
            r"under your control this turn"
        ),
        _this_or_another_entered,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |(?P<another>another )|an? ){_QUALITY} entered "
            rf"the battlefield under your control {_WHEN}"
        ),
        _counted_entered,
    ),
    ConditionReader(
        re.compile(rf"{_SUBJECT} (?:(?P<neg>didn't enter)|entered) (?:the battlefield )?this turn"),
        _subject_entered,
    ),
    # H4
    ConditionReader(
        re.compile(
            # "you've gained 5 or more life this turn" (Case of the Uneaten
            # Feast's "To solve") is the perfect-tense spelling of the same.
            rf"{_WHO}(?:'ve| have| has)? "
            rf"(?P<verbs>(?:gained|lost)(?: (?:and|or) (?:gained|lost))?) {_N_OR_MORE}life {_WHEN}"
        ),
        _life_this_turn,
    ),
    ConditionReader(
        re.compile(rf"{_WHO} (?:didn't|haven't|hasn't) lose? life {_WHEN}"),
        _did_not_lose_life,
    ),
    ConditionReader(
        re.compile(rf"{_WHO} (?P<tail>{_DEALT_DAMAGE_TAIL_RE.pattern})"),
        _player_dealt_damage,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<sources>[a-z ,'-]*?sources?) you controlled dealt {_N_OR_MORE}"
            r"(?P<kind>combat |noncombat )?damage this turn"
        ),
        _sources_dealt_damage,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<count>{COUNT}) or more damage was dealt to "
            r"(?P<subject>it|this creature|this permanent) this turn"
        ),
        _damage_dealt_to_subject,
    ),
    ConditionReader(
        re.compile(
            rf"{_SUBJECT} (?:(?P<neg>didn't deal)|dealt|has dealt) {_N_OR_MORE}"
            r"(?P<kind>combat |noncombat )?damage to "
            r"(?P<to>a player|an opponent|you|that player|them|an? [a-z]+) this turn"
        ),
        _subject_dealt_damage,
    ),
    ConditionReader(
        re.compile(rf"an? {_QUALITY} {_WHO} controlled was dealt excess damage this turn"),
        _excess_damage,
    ),
    ConditionReader(
        re.compile(r"you haven't been dealt combat damage since your last turn"),
        _not_dealt_combat_damage_since_last_turn,
    ),
    ConditionReader(
        re.compile(rf"you(?:'ve| have)? paid or lost (?P<count>{COUNT}) or more \{{e\}} this turn"),
        _energy_paid,
    ),
    # H5
    ConditionReader(
        re.compile(
            rf"you(?:'ve| have)? sacrificed (?:(?P<count>{COUNT}) or more |an? ){_QUALITY} "
            r"this turn"
        ),
        _sacrificed,
    ),
    ConditionReader(
        re.compile(
            rf"{_WHO}(?:'ve| have| has)? discarded (?:(?P<count>{COUNT}) or more cards|"
            r"one or more cards|a card) this turn"
        ),
        _discarded,
    ),
    ConditionReader(
        re.compile(
            rf"{_WHO}(?:'ve| have| has)? (?:drew|drawn) "
            rf"(?:(?P<count>{COUNT}) or more|more than (?P<more_than>{COUNT})) cards? this turn"
        ),
        _drew,
    ),
    ConditionReader(
        re.compile(
            rf"{_WHO}(?:'ve| have| has)? (?:(?P<neg>didn't cast|haven't cast|hasn't cast)|cast) "
            rf"(?P<quant>an?|one or more|another) "
            rf"(?:(?P<quality>[a-z][a-z /,-]*? or [a-z][a-z /,-]*?|[a-z-]+) )?"
            r"spells? this turn"
        ),
        _cast_a_spell,
    ),
    ConditionReader(
        re.compile(
            rf"you(?:'ve| have)? cast a spell with mana value (?P<count>{COUNT}) or "
            r"(?P<cmp>greater|more|less|fewer) this turn"
        ),
        _cast_mana_value,
    ),
    ConditionReader(
        re.compile(
            rf"it (?:was|is|'s) the (?P<ordinal>{ORDINAL}) spell you(?:'ve)? cast this turn"
        ),
        _nth_spell,
    ),
    ConditionReader(
        re.compile(
            rf"it'?s the first time {_KIND}counters have been put on "
            r"(?:that|this) (?:permanent|creature) this turn"
        ),
        _first_time_counters,
    ),
    ConditionReader(
        re.compile(
            rf"an? {_KIND}counter was put on an? (?P<noun>permanent|creature|artifact) "
            r"under your control this turn"
        ),
        _counter_put_on_yours,
    ),
    ConditionReader(
        re.compile(
            rf"you(?:'ve| have)? put an? {_KIND}counter on "
            r"(?P<on>this [a-z]+|an? [a-z]+) this turn"
        ),
        _you_put_a_counter,
    ),
    ConditionReader(re.compile(r"you(?:'ve| have)? committed a crime this turn"), _committed_crime),
    ConditionReader(
        re.compile(
            r"you(?:'ve| have)? played a land or cast a spell this turn from anywhere "
            r"other than your hand"
        ),
        _played_not_from_hand,
    ),
    ConditionReader(
        re.compile(
            r"you (?:(?P<neg>didn't play)|(?:'ve |have )?played) a card from exile this turn"
        ),
        _played_from_exile,
    ),
    ConditionReader(
        re.compile(
            r"you (?:(?P<neg>didn't activate)|(?:'ve |have )?activated) a loyalty ability"
            r"(?: of a planeswalker)? this turn"
        ),
        _loyalty_ability,
    ),
    # Kept from before EC4: Aegar's "a Giant, Wizard, or spell you controlled
    # dealt damage to it this turn" and Urabrask's typed spell count.
    ConditionReader(
        re.compile(
            r"(?P<list>[a-z' ,-]+?) you controlled dealt damage to "
            r"(?:it|that creature|that permanent) this turn"
        ),
        _source_you_controlled_dealt_damage,
    ),
    ConditionReader(
        re.compile(
            rf"you(?:'ve| have) cast (?P<count>{COUNT}) or more (?P<types>[a-z/, ]+?) spells "
            r"this turn"
        ),
        _spells_of_types_cast,
    ),
    # EC7
    ConditionReader(re.compile(r"you created a token this turn"), _created_a_token),
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |an? ){_QUALITY} cards? (?:was|were) put into "
            r"(?P<whose>your|an opponent's) graveyard from anywhere this turn"
        ),
        _card_put_into_graveyard_from_anywhere,
    ),
    # U2
    ConditionReader(
        re.compile(
            rf"(?:(?P<count>{COUNT}) or more |an? |one or more )"
            r"(?P<quality>[a-z-]+(?: [a-z-]+)?) left the battlefield this turn"
        ),
        _left_the_battlefield,
    ),
    ConditionReader(
        re.compile(
            r"a permanent (?:left the battlefield under your control|you controlled left the "
            r"battlefield) this turn"
        ),
        _revolt,
    ),
    ConditionReader(re.compile(r"a spell was warped this turn"), _spell_warped),
    ConditionReader(
        re.compile(
            rf"{_WHO}(?:'ve| have| has)? cast both an? (?P<first>[a-z-]+) spell "
            r"and an? (?P<second>[a-z-]+) spell this turn"
        ),
        _cast_both,
    ),
    ConditionReader(re.compile(r"none of them (?:were|was) cast"), _none_of_them_cast),
    ConditionReader(re.compile(r"no mana was spent to cast them"), _no_mana_spent_to_cast_them),
)


def note_hand_sizes_at_turn_start(game: "Game") -> None:
    """Record every player's hand size as the turn begins - overwritten, not
    added, so a step run twice cannot double it."""
    sizes = game.turn_counts.setdefault(HAND_SIZE_AT_TURN_START, {})
    for player in game.players_in_game:
        sizes[player.username] = len(player.hand)


def hand_size_at_turn_start(game: "Game", username: str) -> int:
    """`username`'s hand size as this turn began. A game that never ran a turn's
    first step (a board assembled mid-turn) has no record, and the hand now is
    the best answer there is."""
    recorded = game.turn_counts.get(HAND_SIZE_AT_TURN_START, {})
    if username in recorded:
        return recorded[username]
    return len(game.player(username).hand)
