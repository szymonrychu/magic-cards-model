"""EP-01 R3 T8: shared amount readers.

`counters_on_it_total` is the one place "N counters on it" is counted: a named
kind ("+1/+1 counter on it") or, with no kind word, every counter on the
object ("for each counter on it"; CR 122.1 - counters are of any kind, and a
phrase naming no kind counts them all). The departed-object half reads last
known information (CR 603.10a), because CR 122.2 has emptied the live counters
by the time a dies trigger resolves.
"""

import contextlib
import contextvars

from ..models.zone import Zone


def counters_on_it_total(subject, kind=None) -> int:
    """Counters of `kind` (all kinds when `None`) on `subject`, last-known when
    it is no longer on the battlefield (CR 603.10a)."""
    counters = subject.counters if subject.zone is Zone.BATTLEFIELD else subject.last_known_counters
    if kind is None:
        return sum(counters.counts.values())
    return counters[kind]


def creatures_blocked_by(game, blocker) -> int:
    """How many attackers `blocker` is blocking right now (CR 509.1a - one
    creature can block several only with an effect that lets it)."""
    return sum(1 for attack in game.combat.attacks if blocker.id in attack.blockers)


def creatures_blocking(game, attacker) -> int:
    """How many creatures are blocking `attacker` right now (CR 509.1g)."""
    attack = game.combat.attack_by(attacker.id)
    return 0 if attack is None else len(attack.blockers)


# --------------------------------------------------------------------------
# The trigger's own event as the referent of "that creature", "its controller",
# "that much", "they" (CR 603.2 - the event that triggered the ability; CR 608.2h
# reads the object as it last existed).
# --------------------------------------------------------------------------


def resolving_event(game):
    """The `GameEvent` that raised the ability now resolving, or `None`."""
    return getattr(game.resolving, "event", None)


def event_referent_permanent(game, ability):
    """The permanent "that creature" / "that planeswalker" names for `ability`.

    A block event names two objects: for "becomes blocked by a creature" the
    blocker is the referent (CR 509.3d), for "blocks" the attacker. A damage
    event's referent is the permanent that was dealt damage when there is one
    (Zagras's "deals combat damage to a planeswalker"), else its source."""
    from .abilities import TriggerEvent

    event = ability.event
    if event is None:
        return None
    condition = getattr(getattr(ability, "ability", None), "condition", "") or ""
    if event.event is TriggerEvent.BLOCKS:
        wanted = event.subject_id if "becomes blocked by" in condition.lower() else event.related_id
    elif event.event is TriggerEvent.DEALS_DAMAGE:
        wanted = event.target_id or event.subject_id
    else:
        wanted = event.subject_id
    return None if wanted is None else game.find_by_id(wanted)


def event_player_username(game, ability, who):
    """The player a trigger's "they" / "that player" / "its controller" names:
    the player the event concerns, or for "its controller" the controller of
    the event's subject (the damage source, the blocker)."""
    event = ability.event
    if event is None:
        return None
    if who in ("its controller", "that creature's controller", "that permanent's controller"):
        if who == "its controller" and event.subject_controller is not None:
            return event.subject_controller
        referent = event_referent_permanent(game, ability)
        return None if referent is None else game.controller_of(referent).username
    return event.player


def cast_spell_mana_value(game):
    """The mana value of the spell a "whenever you cast ..." trigger names, or
    `None` when the resolving ability's event is not a cast (CR 202.3e: the
    event carries the value with X as announced)."""
    from .abilities import TriggerEvent

    event = resolving_event(game)
    if event is None or event.event is not TriggerEvent.CAST_SPELL:
        return None
    if event.amount is not None:
        return int(event.amount)
    spell = None if event.subject_id is None else game.find_by_id(event.subject_id)
    return None if spell is None else int(spell.mana_value)


def event_card_mana_value(game):
    """The mana value of the card the resolving ability's event names - the
    spell of a cast event (`cast_spell_mana_value`) or the card of a discard
    event ("When you discard a card this way, ... its mana value", read as it
    last existed, CR 608.2h) - or `None` when the event names no card."""
    from .abilities import TriggerEvent

    cast_value = cast_spell_mana_value(game)
    if cast_value is not None:
        return cast_value
    event = resolving_event(game)
    if event is None or event.event is not TriggerEvent.DISCARDS_A_CARD or event.subject_id is None:
        return None
    card = game.find_by_id(event.subject_id)
    return None if card is None else int(card.mana_value)


def event_subject_stat(game, *, wants_power):
    """Power (or toughness) of the resolving trigger's event subject as it last
    existed, never negative (CR 107.1b, CR 608.2h)."""
    event = resolving_event(game)
    if event is None or event.subject_id is None:
        return 0
    subject = game.find_by_id(event.subject_id)
    if subject is None:
        return 0
    power, toughness = subject.last_known_power_toughness()
    value = power if wants_power else toughness
    return max(value or 0, 0)


# --------------------------------------------------------------------------
# Event-anaphoric amount terms ("that creature's power", "its mana value" off a
# cast trigger) are meaningful only for a trigger whose event names that
# object. Parsing them everywhere would read a text like "sacrifice another
# creature. When you do, ~ deals damage equal to that creature's power" (where
# "that creature" is the sacrificed one) as the event's subject. A rung that
# knows its whole text is such a trigger turns them on for its own parse only.
# --------------------------------------------------------------------------

_EVENT_TERMS = contextvars.ContextVar("ep01_r3_event_terms", default=False)


def event_terms_enabled() -> bool:
    return _EVENT_TERMS.get()


@contextlib.contextmanager
def event_terms():
    """Parse with the event-anaphoric amount terms on."""
    token = _EVENT_TERMS.set(True)
    try:
        yield
    finally:
        _EVENT_TERMS.reset(token)
