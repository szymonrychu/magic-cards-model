"""EP-01 R3 T8: shared amount readers.

`counters_on_it_total` is the one place "N counters on it" is counted: a named
kind ("+1/+1 counter on it") or, with no kind word, every counter on the
object ("for each counter on it"; CR 122.1 - counters are of any kind, and a
phrase naming no kind counts them all). The departed-object half reads last
known information (CR 603.10a), because CR 122.2 has emptied the live counters
by the time a dies trigger resolves.
"""

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
