"""Scenario: two "enters the battlefield" triggers whose own +1/+1 counter is
conditional on what an earlier sentence in the same ability actually did (CR
400.7's look-back anaphora, CR 118.12's "if you do").

Little Bear: "When this creature enters, untap another target creature you
control. If that creature is a Bear, put a +1/+1 counter on it." - the
counter depends on the untapped target's own *type*.

Mirkwood Nurturer: "When this creature enters, return up to one other target
permanent you control to its owner's hand. If you do, put a +1/+1 counter on
this creature." - the counter depends on whether the return *happened at
all*, on the ability's own source rather than the target.

Verified this session with `mise run rules:find`:

- **CR 608.2b** - a target rechecked as the ability resolves; an illegal or
  absent one (CR 115.6's "up to one" choosing zero) leaves the second
  sentence with nothing to act on.
- **CR 608.2i** - a look-back reader (Little Bear's "that creature") answers
  off the object as it existed a moment before, not after a later
  instruction has moved it.

No off-pool second printing pairs either shape with its own conditional rider
(dated MEMORY.md line): every other Modern/Pioneer/Standard-legal
"untap another target creature you control" (Breaching Hippocamp, Samut,
Voice of Dissent, Taranika, Akroan Veteran) prints no type-conditional
counter afterward, and no legal printing pairs a targeted return with an "if
you do" self-counter the way Mirkwood Nurturer's own sentence does.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_untapping_a_bear_gets_the_counter():
    """Little Bear untaps another Bear it controls: the conditional matches,
    so the +1/+1 counter lands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Little Bear"],
            battlefield=["Forest"] * 3 + ["Runeclaw Bear"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    other_bear = scenario.creature("Runeclaw Bear", "alice")
    other_bear.tap_if_untapped()

    scenario.choose_trigger_targets("Little Bear", [other_bear])
    scenario.cast_and_resolve("Little Bear", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    assert other_bear.tapped is False
    assert other_bear.counters[Counter.PLUS_ONE] == 1


def test_untapping_a_non_bear_gets_no_counter():
    """The identical untap on a Grizzly Bears (a Bear creature by subtype
    too - so Little Bear needs a *non*-Bear target to prove the negative)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Little Bear"],
            battlefield=["Forest"] * 3 + ["Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "alice")
    mystic.tap_if_untapped()

    scenario.choose_trigger_targets("Little Bear", [mystic])
    scenario.cast_and_resolve("Little Bear", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    assert mystic.tapped is False
    assert mystic.counters[Counter.PLUS_ONE] == 0


def test_mirkwood_nurturer_gets_its_own_counter_only_if_it_bounced_something():
    """Bouncing another permanent it controls earns the self counter."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mirkwood Nurturer"],
            battlefield=["Forest"] * 3 + ["Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "alice")

    scenario.choose_trigger_targets("Mirkwood Nurturer", [mystic])
    scenario.cast_and_resolve("Mirkwood Nurturer", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    assert mystic.zone is Zone.HAND
    nurturer = scenario.creature("Mirkwood Nurturer", "alice")
    assert nurturer.counters[Counter.PLUS_ONE] == 1


def test_mirkwood_nurturer_gets_no_counter_when_it_bounces_nothing():
    """CR 115.6: choosing zero targets for "up to one" means the whole "if
    you do" consequence is skipped."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mirkwood Nurturer"], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Mirkwood Nurturer", [])
    scenario.cast_and_resolve("Mirkwood Nurturer", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    nurturer = scenario.creature("Mirkwood Nurturer", "alice")
    assert nurturer.counters[Counter.PLUS_ONE] == 0
